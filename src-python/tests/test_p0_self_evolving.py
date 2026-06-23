"""P0 单元测试: SkillQualityGate + LifecycleManager + FailureSkillGenerator"""
from __future__ import annotations

import json
import os
import textwrap
from datetime import datetime, timedelta, timezone

import pytest

from app.services.skill_engine.quality_gate import (
    SkillQualityGate,
    GateResult,
    GateSummary,
    _split_frontmatter,
    _extract_sections,
)
from app.services.skill_engine.lifecycle_manager import (
    LifecycleManager,
    SkillLifecycleEntry,
    PROMOTE_MIN_AGE_HOURS,
)
from app.services.skill_engine.failure_skill_generator import (
    FailureSkillGenerator,
    _extract_failure_signals,
)


# ============ Fixtures ============

VALID_SKILL_MD = textwrap.dedent("""\
    ---
    name: exploit-fakesvc-v1
    description: 利用 fakesvc 1.0 的命令注入漏洞
    domain: penetration-testing
    subdomain: exploitation
    tags: [fakesvc, rce]
    version: '2.0'
    ---
    ## Principle

    fakesvc 1.0 在 /api/run 接口未对 cmd 参数做过滤。

    ## Detection Fingerprint

    1. 服务 Banner 包含 'fakesvc/1.0'
    2. /api/run 返回 200

    反例: fakesvc 1.1+ 已修复

    ## Workflow

    `curl http://target:8080/api/run?cmd=id`

    ## Failure Modes

    | 现象 | 原因 |
    |------|------|
    | 403 | WAF |

    ## Generalization

    适用于所有 fakesvc 1.x 版本
""")


@pytest.fixture
def tmp_skills_root(tmp_path):
    root = tmp_path / "skills"
    (root / "learned" / "draft").mkdir(parents=True)
    (root / "learned" / "active").mkdir(parents=True)
    (root / "learned" / "deprecated").mkdir(parents=True)
    return str(root)


@pytest.fixture
def valid_skill_file(tmp_skills_root):
    path = os.path.join(tmp_skills_root, "learned", "draft", "exploit-fakesvc-v1.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(VALID_SKILL_MD)
    return path


# ============ QualityGate tests ============

def test_split_frontmatter_parses_basic_keys():
    meta, body = _split_frontmatter(VALID_SKILL_MD)
    assert meta["name"] == "exploit-fakesvc-v1"
    assert meta["domain"] == "penetration-testing"
    assert "## Principle" in body


def test_extract_sections_finds_all_v2_sections():
    _, body = _split_frontmatter(VALID_SKILL_MD)
    sections = _extract_sections(body)
    for s in ("Principle", "Detection Fingerprint", "Workflow", "Failure Modes", "Generalization"):
        assert s in sections


def test_quality_gate_accepts_valid_skill(valid_skill_file):
    gate = SkillQualityGate()
    result = gate.check(valid_skill_file)
    assert result.accepted, f"Should accept but rejected: {result.rejected_reasons}"


def test_quality_gate_rejects_missing_frontmatter_keys(tmp_skills_root):
    bad = textwrap.dedent("""\
        ---
        name: bad-skill
        ---
        ## Principle
        x
        ## Detection Fingerprint
        x
        ## Workflow
        x
        ## Failure Modes
        x
        ## Generalization
        x
    """)
    path = os.path.join(tmp_skills_root, "bad.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(bad)
    gate = SkillQualityGate()
    result = gate.check(path)
    assert not result.accepted
    assert any("frontmatter" in r for r in result.rejected_reasons)


def test_quality_gate_rejects_missing_v2_sections(tmp_skills_root):
    incomplete = textwrap.dedent("""\
        ---
        name: incomplete
        description: x
        domain: x
        subdomain: x
        version: '2.0'
        ---
        ## Principle
        x
    """)
    path = os.path.join(tmp_skills_root, "incomplete.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(incomplete)
    gate = SkillQualityGate()
    result = gate.check(path)
    assert not result.accepted
    assert any("章节" in r for r in result.rejected_reasons)


def test_quality_gate_grounding_warns_when_cve_not_in_evidence(tmp_skills_root):
    skill = VALID_SKILL_MD.replace("## Principle\n", "## Principle\n参考 CVE-2099-9999\n")
    path = os.path.join(tmp_skills_root, "with_cve.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(skill)
    gate = SkillQualityGate(state_evidence={"cves": set()})  # 无证据
    result = gate.check(path)
    assert result.accepted, "P0 grounding 仅警告，不应拒绝"
    assert any("grounding" in w for w in result.warnings)


def test_quality_gate_grounding_rejects_when_enforced(tmp_skills_root):
    skill = VALID_SKILL_MD.replace("## Principle\n", "## Principle\n参考 CVE-2099-9999\n")
    path = os.path.join(tmp_skills_root, "with_cve.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(skill)
    gate = SkillQualityGate(state_evidence={"cves": set()}, enforce_grounding=True)
    result = gate.check(path)
    assert not result.accepted
    assert any("grounding" in r for r in result.rejected_reasons)


def test_quality_gate_filter_returns_summary(tmp_skills_root, valid_skill_file):
    # 第二个文件: 无效
    bad = os.path.join(tmp_skills_root, "bad.md")
    with open(bad, "w", encoding="utf-8") as f:
        f.write("not a valid skill")
    gate = SkillQualityGate()
    summary = gate.filter([valid_skill_file, bad])
    assert valid_skill_file in summary.accepted
    assert len(summary.rejected) == 1


# ============ LifecycleManager tests ============

def test_lifecycle_register_draft(tmp_skills_root):
    lc = LifecycleManager(tmp_skills_root)
    lc.ensure_dirs()
    path = os.path.join(tmp_skills_root, "learned", "draft", "x.md")
    open(path, "w").close()
    entry = lc.register_draft("x", path)
    assert entry.status == "draft"
    assert lc.get_status("x") == "draft"


def test_lifecycle_record_use_increments(tmp_skills_root):
    lc = LifecycleManager(tmp_skills_root)
    lc.ensure_dirs()
    path = os.path.join(tmp_skills_root, "learned", "draft", "x.md")
    open(path, "w").close()
    lc.register_draft("x", path)
    lc.record_use("x", success=True)
    lc.record_use("x", success=True)
    data = lc._load()
    assert data["x"].used_count == 2
    assert data["x"].successful_uses == 2


def test_lifecycle_promotes_after_threshold(tmp_skills_root):
    lc = LifecycleManager(tmp_skills_root)
    lc.ensure_dirs()
    path = os.path.join(tmp_skills_root, "learned", "draft", "x.md")
    with open(path, "w") as f:
        f.write("dummy")

    # 手动登记一条满足晋升条件的 entry（created_at 设为 2 天前）
    lc._load()  # 触发 cache
    old_time = (datetime.now(timezone.utc) - timedelta(hours=PROMOTE_MIN_AGE_HOURS + 2)).isoformat()
    lc._cache["x"] = SkillLifecycleEntry(
        status="draft",
        created_at=old_time,
        used_count=2,
        successful_uses=2,
        current_path=path,
    )
    lc._save(lc._cache)

    result = lc.auto_maintenance()
    assert "x" in result["promoted"]
    # 文件应移到 active 目录
    new_path = os.path.join(tmp_skills_root, "learned", "active", "x.md")
    assert os.path.isfile(new_path)
    assert not os.path.isfile(path)
    assert lc.get_status("x") == "active"


def test_lifecycle_persists_to_json(tmp_skills_root):
    lc = LifecycleManager(tmp_skills_root)
    lc.ensure_dirs()
    lc.register_draft("y", os.path.join(tmp_skills_root, "y.md"))

    lc2 = LifecycleManager(tmp_skills_root)
    assert lc2.get_status("y") == "draft"


# ============ FailureSkillGenerator tests ============

class _FakeState:
    def __init__(self, data):
        self.data = data


def test_failure_signal_extraction_needs_three_occurrences():
    state = _FakeState({
        "actions_taken": [
            {"status": "failed", "service": "ssh", "tool": "hydra",
             "failure_reason": "auth-failed", "target": "1.1.1.1", "port": 22},
            {"status": "failed", "service": "ssh", "tool": "hydra",
             "failure_reason": "auth-failed", "target": "1.1.1.1", "port": 22},
            {"status": "failed", "service": "ssh", "tool": "hydra",
             "failure_reason": "auth-failed", "target": "1.1.1.1", "port": 22},
        ],
        "attack_surfaces": [],
        "targets": ["1.1.1.1"],
    })
    signals = _extract_failure_signals(state)
    assert len(signals) == 1
    assert signals[0]["occurrences"] == 3


def test_failure_signal_skips_below_threshold():
    state = _FakeState({
        "actions_taken": [
            {"status": "failed", "service": "ftp", "tool": "hydra",
             "failure_reason": "x"},
            {"status": "failed", "service": "ftp", "tool": "hydra",
             "failure_reason": "x"},
        ],
        "attack_surfaces": [],
        "targets": [],
    })
    assert _extract_failure_signals(state) == []


def test_failure_skill_generator_writes_md(tmp_skills_root):
    state = _FakeState({
        "actions_taken": [
            {"status": "failed", "service": "smb", "tool": "enum4linux",
             "failure_reason": "access-denied", "target": "1.1.1.1", "port": 445,
             "error": "NT_STATUS_ACCESS_DENIED"},
        ] * 3,
        "attack_surfaces": [],
        "targets": ["1.1.1.1"],
    })
    gen = FailureSkillGenerator(tmp_skills_root)
    paths = gen.generate_from_state(state)
    assert len(paths) == 1
    assert "failure-smb-enum4linux-access-denied" in paths[0]
    with open(paths[0], "r", encoding="utf-8") as f:
        content = f.read()
    assert "## Principle" in content
    assert "## Detection Fingerprint" in content
    assert "## Failure Modes" in content
    assert "## Generalization" in content


# ============ 集成测试 ============

def test_loader_picks_up_learned_draft(tmp_skills_root):
    """SkillLoader 应识别 learned/draft 子目录"""
    from app.services.skill_engine import SkillLoader
    path = os.path.join(tmp_skills_root, "learned", "draft", "exploit-fakesvc-v1.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(VALID_SKILL_MD)
    loader = SkillLoader(tmp_skills_root)
    skills = loader.load_all()
    names = [s.name for s in skills]
    assert "exploit-fakesvc-v1" in names


def test_loader_ignores_learned_deprecated(tmp_skills_root):
    """SkillLoader 不应加载 deprecated 子目录"""
    from app.services.skill_engine import SkillLoader
    dep_path = os.path.join(tmp_skills_root, "learned", "deprecated", "old.md")
    with open(dep_path, "w", encoding="utf-8") as f:
        f.write(VALID_SKILL_MD.replace("exploit-fakesvc-v1", "old"))
    loader = SkillLoader(tmp_skills_root)
    names = [s.name for s in loader.load_all()]
    assert "old" not in names
