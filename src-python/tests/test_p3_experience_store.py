"""P3 单元测试: ExperienceStore + State.build_target_fingerprint + recon-time injection"""
from __future__ import annotations

import json
import os

import pytest

from app.services.experience_store import ExperienceStore, ExperienceEntry
from app.services.experience_store.store import (
    _fingerprint_text,
    _hash_fingerprint,
)


# ============ Fingerprint tests ============

def test_fingerprint_text_stable_ordering():
    fp1 = {"os": "Linux", "services": ["ftp", "ssh"], "versions": ["v1"], "open_ports": [21, 22]}
    fp2 = {"os": "Linux", "services": ["ssh", "ftp"], "versions": ["v1"], "open_ports": [22, 21]}
    assert _fingerprint_text(fp1) == _fingerprint_text(fp2)


def test_fingerprint_hash_matches_when_equivalent():
    fp1 = {"os": "Linux", "services": ["ftp"], "versions": [], "open_ports": [21]}
    fp2 = {"os": "Linux", "services": ["ftp"], "versions": [], "open_ports": [21]}
    assert _hash_fingerprint(fp1) == _hash_fingerprint(fp2)


def test_fingerprint_hash_differs_for_different_envs():
    fp1 = {"os": "Linux", "services": ["ftp"], "versions": [], "open_ports": [21]}
    fp2 = {"os": "Windows", "services": ["smb"], "versions": [], "open_ports": [445]}
    assert _hash_fingerprint(fp1) != _hash_fingerprint(fp2)


# ============ State.build_target_fingerprint ============

def test_state_build_fingerprint(tmp_path):
    from app.services.pentest_agent.state import State
    state = State(str(tmp_path / "state.json"))
    state.data["findings"] = [
        {"service": "ftp", "port": 21, "version": "vsftpd 2.3.4"},
        {"service": "ssh", "port": 22, "version": "OpenSSH 4.7"},
        {"service": "ssh", "port": 22, "version": "OpenSSH 4.7"},  # duplicate
    ]
    fp = state.build_target_fingerprint()
    assert "ftp" in fp["services"]
    assert "ssh" in fp["services"]
    assert 21 in fp["open_ports"]
    assert 22 in fp["open_ports"]
    assert "vsftpd 2.3.4" in fp["versions"]


def test_state_attach_history_context(tmp_path):
    from app.services.pentest_agent.state import State
    state = State(str(tmp_path / "state.json"))
    state.attach_history_context("## 历史经验\n- 相似环境曾通过 vsftpd backdoor 拿到 shell")
    assert "vsftpd backdoor" in state.get_history_context()


def test_state_llm_context_includes_history(tmp_path):
    """llm_context() 应当注入 history_context 区块"""
    from app.services.pentest_agent.state import State
    state = State(str(tmp_path / "state.json"))
    state.data["targets"] = ["192.168.1.10"]
    state.attach_history_context("HISTORICAL EXPERIENCE BLOCK")
    ctx = state.llm_context()
    assert "HISTORICAL EXPERIENCE BLOCK" in ctx


# ============ ExperienceStore ============

@pytest.fixture
def skills_root(tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    return str(root)


def test_store_add_and_load(skills_root):
    store = ExperienceStore(skills_root)
    fp = {"os": "Linux", "services": ["ftp"], "versions": ["vsftpd 2.3.4"], "open_ports": [21]}
    entry = store.add(
        target_fingerprint=fp,
        outcome="compromised",
        successful_paths=[{"surface": "1.1.1.1:21/ftp", "tool": "msfconsole"}],
        duration_rounds=5,
    )
    assert entry.id
    assert entry.outcome == "compromised"
    # 文件应已保存
    entries = store.list_entries()
    assert len(entries) == 1


def test_store_dedupes_by_fingerprint(skills_root):
    store = ExperienceStore(skills_root)
    fp = {"os": "Linux", "services": ["ftp"], "versions": [], "open_ports": [21]}
    e1 = store.add(target_fingerprint=fp, outcome="no-progress")
    e2 = store.add(target_fingerprint=fp, outcome="compromised")  # 同指纹
    entries = store.list_entries()
    assert len(entries) == 1
    # 应保留最新的
    assert entries[0]["id"] == e2.id


def test_store_query_exact_fingerprint_returns_top_score(skills_root):
    store = ExperienceStore(skills_root)
    fp = {"os": "Linux", "services": ["ftp", "ssh"], "versions": [], "open_ports": [21, 22]}
    store.add(target_fingerprint=fp, outcome="compromised",
              successful_paths=[{"surface": "x", "tool": "msf"}])

    # 完全相同指纹查询
    hits = store.query_similar_env(fp, top_k=3)
    assert len(hits) >= 1
    entry, score = hits[0]
    assert score == 1.0
    assert entry.outcome == "compromised"


def test_store_query_returns_empty_for_unrelated_env(skills_root):
    store = ExperienceStore(skills_root)
    fp1 = {"os": "Linux", "services": ["ftp"], "versions": [], "open_ports": [21]}
    store.add(target_fingerprint=fp1, outcome="compromised")
    # 查询完全不同环境（无完全匹配 + 低相似度）
    fp2 = {"os": "Windows", "services": ["smb"], "versions": [], "open_ports": [445]}
    hits = store.query_similar_env(fp2, top_k=3, min_score=0.9)
    # 不允许 1.0（完全匹配 fp_hash），且 embedding 应低于 0.9
    assert all(score < 1.0 for _, score in hits)


def test_store_render_for_prompt(skills_root):
    store = ExperienceStore(skills_root)
    fp = {"os": "Linux", "services": ["ftp"], "versions": [], "open_ports": [21]}
    store.add(
        target_fingerprint=fp,
        outcome="compromised",
        successful_paths=[{"surface": "1.1.1.1:21/ftp", "tool": "msfconsole"}],
        recommendations=["next time try anonymous login first"],
    )
    hits = store.query_similar_env(fp, top_k=3)
    rendered = store.render_for_prompt(hits)
    assert "## 历史相似环境经验" in rendered
    assert "compromised" in rendered
    assert "msfconsole" in rendered or "ftp" in rendered


def test_store_delete_entry(skills_root):
    store = ExperienceStore(skills_root)
    fp = {"os": "Linux", "services": ["x"], "versions": [], "open_ports": [1]}
    e = store.add(target_fingerprint=fp, outcome="no-progress")
    assert store.delete_entry(e.id)
    assert len(store.list_entries()) == 0


def test_store_persistence_across_instances(skills_root):
    store = ExperienceStore(skills_root)
    fp = {"os": "Linux", "services": ["y"], "versions": [], "open_ports": [2]}
    e = store.add(target_fingerprint=fp, outcome="compromised")

    # 用新实例加载
    store2 = ExperienceStore(skills_root)
    entries = store2.list_entries()
    assert any(m["id"] == e.id for m in entries)


# ============ ExperienceEntry round-trip ============

def test_experience_entry_from_dict_roundtrip():
    src = {
        "id": "abc",
        "timestamp": "2026-06-24T00:00:00",
        "target_fingerprint": {"os": "Linux"},
        "fingerprint_hash": "hash",
        "outcome": "compromised",
        "duration_rounds": 10,
        "successful_paths": [{"x": "y"}],
        "failed_attempts": [],
        "skills_used": ["s1"],
        "recommendations": ["r1"],
        "notes": "n",
    }
    e = ExperienceEntry.from_dict(src)
    assert e.id == "abc"
    assert e.outcome == "compromised"
    assert e.successful_paths == [{"x": "y"}]
    assert e.skills_used == ["s1"]
