"""P4 单元测试: 验证 SkillGenerator fallback 模板符合 QualityGate 要求"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from app.services.skill_engine.skill_generator import SkillGenerator
from app.services.skill_engine.failure_skill_generator import (
    FailureSkillGenerator,
    _extract_failure_signals,
)
from app.services.skill_engine.quality_gate import SkillQualityGate
from app.services.pentest_agent.reflection import StructuredEvaluator


# --- P4-2: fallback 模板必须包含 v2 五段 ---

@pytest.fixture
def tmp_skills(tmp_path):
    root = tmp_path / "skills"
    (root / "learned" / "draft").mkdir(parents=True)
    (root / "learned" / "active").mkdir(parents=True)
    return str(root)


def _sample_path(exploit_success=True):
    return {
        "name": "exploit-vsftpd-234-test",
        "port": 21,
        "service": "vsftpd 2.3.4",
        "tag": "ftp",
        "ip": "1.2.3.4",
        "exploit_success": exploit_success,
        "credentials": [{"username": "anonymous", "password": "", "source": "auto"}],
        "vulnerabilities": [{"cve": "CVE-2011-2523", "severity": "critical", "name": "vsftpd backdoor"}],
        "commands": [
            {"tool": "msfconsole", "args": "use exploit/unix/ftp/vsftpd_234_backdoor; set RHOSTS 1.2.3.4; run",
             "result": "Command shell session 1 opened"},
        ],
        "failures": [],
        "sessions": [{"id": "s1", "active": True}],
    }


def test_p4_2_fallback_template_has_all_v2_sections(tmp_skills):
    """fallback 模板必须包含 5 个 v2 必需章节"""
    gen = SkillGenerator(tmp_skills)
    md = gen._render_skill_md(_sample_path())
    assert "## Principle" in md, f"缺 Principle:\n{md[:500]}"
    assert "## Detection Fingerprint" in md, f"缺 Detection Fingerprint:\n{md[:500]}"
    assert "## Workflow" in md
    assert "## Failure Modes" in md
    assert "## Generalization" in md


def test_p4_2_fallback_frontmatter_is_v2(tmp_skills):
    """fallback 模板 frontmatter version 必须是 '2.0'"""
    gen = SkillGenerator(tmp_skills)
    md = gen._render_skill_md(_sample_path())
    assert "version: '2.0'" in md, f"frontmatter 不是 2.0:\n{md[:400]}"
    for key in ("name:", "description:", "domain:", "subdomain:"):
        assert key in md, f"缺 frontmatter 字段 {key}"


def test_p4_2_fallback_passes_quality_gate(tmp_skills):
    """关键测试: fallback 生成的 skill 必须能过 SkillQualityGate"""
    gen = SkillGenerator(tmp_skills)
    md = gen._render_skill_md(_sample_path())
    # 写到临时文件
    skill_path = Path(tmp_skills) / "learned" / "draft" / "exploit-vsftpd-234-test.md"
    skill_path.write_text(md, encoding="utf-8")
    gate = SkillQualityGate()
    result = gate.check(str(skill_path))
    assert result.accepted, (
        f"fallback 应通过 QualityGate, 拒绝原因={result.rejected_reasons}\n"
        f"warnings={result.warnings}"
    )


def test_p4_3_summary_skill_passes_quality_gate(tmp_skills):
    """汇总 skill 也必须过 QualityGate"""
    gen = SkillGenerator(tmp_skills)
    md = gen._render_summary_skill([_sample_path(), _sample_path(exploit_success=False)], ["1.2.3.4"])
    skill_path = Path(tmp_skills) / "learned" / "draft" / "pentest-summary.md"
    skill_path.write_text(md, encoding="utf-8")
    gate = SkillQualityGate()
    result = gate.check(str(skill_path))
    assert result.accepted, f"summary 被拒: {result.rejected_reasons}"


# --- P4-1: _call_llm 适配 async chat(system, user) ---

def test_p4_1_call_llm_uses_async_chat(tmp_skills):
    """SkillGenerator._call_llm 应当能调用 async chat(system, user)"""
    class FakeAsyncClient:
        async def chat(self, system, user):
            return f"SYS:{system[:30]} USR:{user[:30]}"

    gen = SkillGenerator(tmp_skills, llm_client=FakeAsyncClient())
    result = gen._call_llm([
        {"role": "system", "content": "you are a tester"},
        {"role": "user", "content": "make a thing"},
    ])
    assert result is not None
    assert "SYS:you are a tester" in result
    assert "USR:make a thing" in result


def test_p4_1_call_llm_handles_async_failure(tmp_skills):
    """async chat raise 时应优雅 fallback (不崩)"""
    class BrokenClient:
        async def chat(self, system, user):
            raise RuntimeError("API down")

    gen = SkillGenerator(tmp_skills, llm_client=BrokenClient())
    result = gen._call_llm([{"role": "user", "content": "x"}])
    assert result is None


# --- P4-4: FailureSkillGenerator 不应再产生 unknown-multiple ---

def test_p4_4_failure_signals_use_surface_key():
    """state.actions_taken 使用 surface_key+ports 时应正确推断 service"""
    class _S:
        data = {
            "actions_taken": [
                # 真实 SDIT actions_taken 结构（HTTP probe）
                {"status": "failed", "tool": "curl",
                 "surface_key": "192.168.1.10|80,8080",
                 "ports": [80, 8080],
                 "surface": "Web",
                 "args": "-sI -m 5 http://192.168.1.10:80",
                 "error": "Connection refused"},
                {"status": "failed", "tool": "curl",
                 "surface_key": "192.168.1.10|80,8080",
                 "ports": [80, 8080],
                 "surface": "Web",
                 "args": "-sI -m 5 http://192.168.1.10:80",
                 "error": "Connection refused"},
                {"status": "failed", "tool": "curl",
                 "surface_key": "192.168.1.10|80,8080",
                 "ports": [80, 8080],
                 "surface": "Web",
                 "args": "-sI -m 5 http://192.168.1.10:80",
                 "error": "Connection refused"},
            ],
            "attack_surfaces": [],
            "targets": ["192.168.1.10"],
        }
    sigs = _extract_failure_signals(_S())
    assert len(sigs) == 1, f"应识别 1 个 failure signal, got {len(sigs)}"
    s = sigs[0]
    assert s["service"] == "http", f"service 推断错误: {s['service']}"
    assert s["tool"] == "curl"
    assert s["occurrences"] == 3
    assert "192.168.1.10" in s["target_fingerprint"]


# --- P4-5: StructuredEvaluator 应能从 surface_key 提取 surface ---

def test_p4_5_evaluator_extracts_surface_from_surface_key():
    """evaluator 应当从 surface_key+ports 拿到真正的 ip:port"""
    class _S:
        data = {
            "actions_taken": [
                {"status": "completed", "action_type": "exploit",
                 "tool": "msfconsole",
                 "surface_key": "192.168.1.10|21",
                 "ports": [21],
                 "args": "use exploit/unix/ftp/vsftpd_234_backdoor; set RHOSTS 192.168.1.10",
                 "round": 5,
                 "evidence": ["session opened"],
                 "session_obtained": True,
                 "full_stdout": "Command shell session 1 opened on 192.168.1.10:21"},
                {"status": "failed", "tool": "hydra",
                 "surface_key": "192.168.1.10|22",
                 "ports": [22],
                 "args": "ssh://192.168.1.10 -L users.txt -P pwds.txt",
                 "failure_reason": "auth-failed"},
            ],
            "attack_surfaces": [],
            "targets": ["192.168.1.10"],
            "round_plans": [{"round": 1}],
            "sessions": [],
            "vulnerabilities": [],
            "credentials": [],
        }
    ev = StructuredEvaluator().evaluate(_S())
    # 成功路径的 surface 应当有真实 ip:port
    assert len(ev.successful_paths) >= 1
    sp = ev.successful_paths[0]
    assert "192.168.1.10" in sp.surface, f"surface 没解析到 ip: {sp.surface}"
    assert "21" in sp.surface, f"surface 没解析到 port: {sp.surface}"
    assert sp.service != "unknown", f"service 没推断: {sp.service}"
