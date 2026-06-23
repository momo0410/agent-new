"""P2 单元测试: Reflection Phase + StructuredEvaluator + LLMReflector"""
from __future__ import annotations

import json
import os
import textwrap
from unittest.mock import MagicMock

import pytest

from app.services.pentest_agent.reflection import (
    StructuredEvaluator,
    StructuredEvaluation,
    AttackPath,
    FailedPath,
    UnexploredSurface,
    LLMReflector,
    LLMInsights,
    ReflectionReport,
    run_reflection,
)


# ============ Fake state ============

class _FakeState:
    def __init__(self, data):
        self.data = data

    def set_phase(self, phase):
        self.data["phase"] = phase

    def add_milestone(self, kind, msg):
        self.data.setdefault("milestones", []).append({"kind": kind, "msg": msg})

    def generate_report(self):
        return "fake-report.md"


def _make_state(**overrides):
    base = {
        "phase": "post",
        "targets": ["192.168.1.10"],
        "findings": [
            {"service": "ftp", "port": 21, "version": "vsftpd 2.3.4"},
            {"service": "ssh", "port": 22, "version": "OpenSSH 4.7"},
        ],
        "vulnerabilities": [
            {"cve": "CVE-2011-2523", "service": "ftp", "severity": "critical"},
        ],
        "credentials": [],
        "actions_taken": [
            # 成功 exploit
            {"status": "completed", "action_type": "exploit",
             "service": "ftp", "tool": "msfconsole", "target": "192.168.1.10", "port": 21,
             "round": 5, "evidence": ["got shell on target"],
             "session_obtained": True},
            # 失败重复 3 次
            {"status": "failed", "service": "ssh", "tool": "hydra",
             "failure_reason": "auth-failed", "target": "192.168.1.10", "port": 22,
             "error": "no valid creds"},
            {"status": "failed", "service": "ssh", "tool": "hydra",
             "failure_reason": "auth-failed", "target": "192.168.1.10", "port": 22},
            {"status": "failed", "service": "ssh", "tool": "hydra",
             "failure_reason": "auth-failed", "target": "192.168.1.10", "port": 22},
        ],
        "attack_surfaces": [
            {"ip": "192.168.1.10", "port": 80, "service": "http", "score": 8, "status": "discovered"},
        ],
        "sessions": [{"id": 1, "active": True}],
        "round_plans": [{"round": i} for i in range(10)],
    }
    base.update(overrides)
    return _FakeState(base)


# ============ Evaluator tests ============

def test_evaluator_extracts_successful_paths():
    ev = StructuredEvaluator().evaluate(_make_state())
    assert len(ev.successful_paths) >= 1
    assert ev.successful_paths[0].service == "ftp"
    assert ev.successful_paths[0].success_tool == "msfconsole"


def test_evaluator_extracts_failed_paths():
    ev = StructuredEvaluator().evaluate(_make_state())
    assert len(ev.failed_paths) >= 1
    fp = ev.failed_paths[0]
    assert fp.service == "ssh"
    assert fp.failure_reason == "auth-failed"
    assert fp.occurrences == 3
    assert "hydra" in fp.failed_tools


def test_evaluator_extracts_unexplored():
    ev = StructuredEvaluator().evaluate(_make_state())
    assert len(ev.unexplored) >= 1
    assert ev.unexplored[0].service == "http"


def test_evaluator_classifies_outcome_compromised():
    ev = StructuredEvaluator().evaluate(_make_state())
    assert ev.outcome == "compromised"  # 有活跃 session


def test_evaluator_outcome_no_progress():
    state = _make_state(
        actions_taken=[],
        sessions=[],
        vulnerabilities=[],
        attack_surfaces=[],
    )
    ev = StructuredEvaluator().evaluate(state)
    assert ev.outcome == "no-progress"
    assert not ev.has_signal()


# ============ LLMReflector tests ============

def test_llm_reflector_skips_when_no_signal():
    state_empty = _make_state(
        actions_taken=[], sessions=[], vulnerabilities=[], attack_surfaces=[],
    )
    ev = StructuredEvaluator().evaluate(state_empty)
    mock = MagicMock(return_value="should not be called")
    reflector = LLMReflector(llm_callable=mock)
    assert reflector.reflect(ev) is None
    mock.assert_not_called()


def test_llm_reflector_parses_json_response():
    ev = StructuredEvaluator().evaluate(_make_state())
    fake_response = json.dumps({
        "root_cause_analysis": [
            {"failure": "ssh hydra", "likely_cause": "weak password list",
             "evidence_line": "auth-failed x3"}
        ],
        "generalizable_patterns": [
            {"pattern": "vsftpd 2.3.4 backdoor", "applies_when": "any vsftpd 2.3.x",
             "skill_name_hint": "exploit-vsftpd-backdoor"}
        ],
        "recommendations_for_next_run": [
            "Use larger password dictionary",
        ],
    })
    reflector = LLMReflector(llm_callable=lambda s, u: fake_response)
    insights = reflector.reflect(ev)
    assert insights is not None
    assert len(insights.root_cause_analysis) == 1
    assert len(insights.generalizable_patterns) == 1
    assert len(insights.recommendations_for_next_run) == 1


def test_llm_reflector_handles_json_in_text_wrapping():
    """LLM 经常用 ```json ... ``` 包裹响应"""
    ev = StructuredEvaluator().evaluate(_make_state())
    fake = """好的，我看完了，下面是分析：
    
```json
{
    "root_cause_analysis": [],
    "generalizable_patterns": [{"pattern":"P","applies_when":"W","skill_name_hint":"H"}],
    "recommendations_for_next_run": ["R"]
}
```
希望有帮助。"""
    reflector = LLMReflector(llm_callable=lambda s, u: fake)
    insights = reflector.reflect(ev)
    assert insights is not None
    assert len(insights.generalizable_patterns) == 1


def test_llm_reflector_keeps_raw_when_json_invalid():
    ev = StructuredEvaluator().evaluate(_make_state())
    reflector = LLMReflector(llm_callable=lambda s, u: "garbage output not json")
    insights = reflector.reflect(ev)
    assert insights is not None
    assert insights.raw_response.startswith("garbage")
    # 解析失败应当返回空列表而非崩溃
    assert insights.root_cause_analysis == []


def test_llm_reflector_handles_call_exception():
    ev = StructuredEvaluator().evaluate(_make_state())
    def boom(s, u):
        raise RuntimeError("API down")
    reflector = LLMReflector(llm_callable=boom)
    assert reflector.reflect(ev) is None


def test_llm_reflector_disabled_when_no_llm():
    ev = StructuredEvaluator().evaluate(_make_state())
    reflector = LLMReflector(llm_callable=None)
    assert reflector.reflect(ev) is None


# ============ run_reflection 集成测试 ============

def test_run_reflection_produces_report(tmp_path):
    state = _make_state()
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    (skills_root / "learned" / "draft").mkdir(parents=True)
    report_dir = tmp_path / "reports"
    report_dir.mkdir()

    report = run_reflection(
        state=state,
        skills_root=str(skills_root),
        llm_callable=None,
        report_dir=str(report_dir),
    )
    assert isinstance(report, ReflectionReport)
    assert report.evaluation.outcome == "compromised"
    # report file should be saved
    json_files = list(report_dir.glob("reflection_*.json"))
    assert len(json_files) == 1
    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["evaluation"]["outcome"] == "compromised"


def test_run_reflection_works_without_signals(tmp_path):
    state = _make_state(
        actions_taken=[], sessions=[], vulnerabilities=[],
        attack_surfaces=[],
    )
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    (skills_root / "learned" / "draft").mkdir(parents=True)
    report = run_reflection(
        state=state,
        skills_root=str(skills_root),
        llm_callable=None,
    )
    assert report.evaluation.outcome == "no-progress"
    assert report.llm_insights is None
    assert report.skills_written == []


def test_phase_order_includes_reflection():
    from app.services.pentest_agent.state import PHASE_ORDER
    assert "reflection" in PHASE_ORDER
    # reflection 必须在 done 之前
    assert PHASE_ORDER.index("reflection") < PHASE_ORDER.index("done")
    # reflection 应在 lateral 之后
    assert PHASE_ORDER.index("reflection") > PHASE_ORDER.index("lateral")
