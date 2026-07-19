from __future__ import annotations

import asyncio
import json

from app.core.choice_reason import summarize_choice_reason
from app.routers import api
from app.services.pentest_agent.state import State


def test_choice_reason_removes_private_and_tool_blocks():
    value = (
        "<thinking>PRIVATE_CHAIN step one step two</thinking>"
        "<tool>hidden invocation</tool>"
    )
    summary = summarize_choice_reason(value, "根据端口与服务证据验证目标")
    assert summary == "根据端口与服务证据验证目标"
    assert "PRIVATE_CHAIN" not in summary
    assert "hidden invocation" not in summary
    assert len(summarize_choice_reason("observable factor " * 100)) <= 240


def test_action_api_exposes_choice_reason_not_internal_record(monkeypatch, tmp_path):
    state_path = tmp_path / "pentest_state_choice-reason.json"
    state = State(str(state_path))
    state.start_action(
        "probe",
        "TARGET",
        llm_decision="<thinking>PRIVATE_CHAIN</thinking>",
        purpose="验证已观察到的服务指纹",
    )
    monkeypatch.setitem(
        api._pentest_tasks,
        "choice-reason",
        {"state_file": str(state_path), "status": "running", "task_obj": None},
    )
    logs = asyncio.run(api.pentest_logs("choice-reason"))
    action = logs["actions"][0]
    assert action["choice_reason"] == "验证已观察到的服务指纹"
    assert "llm_decision" not in action
    assert "PRIVATE_CHAIN" not in json.dumps(logs, ensure_ascii=False)

