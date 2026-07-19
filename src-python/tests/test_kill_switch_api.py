from __future__ import annotations

import asyncio

from app.core.mission_control import MissionControl
from app.core.scope_policy import ScopePolicy
from app.routers import api
from app.services.pentest_agent.state import State


def test_global_kill_switch_propagates_to_live_missions(monkeypatch, tmp_path):
    policy = ScopePolicy(b"fixture-kill-switch-secret".ljust(32, b"x"))
    monkeypatch.setattr(api, "_pentest_scope_policy", policy)
    state_path = tmp_path / "pentest_state_kill.json"
    State(str(state_path))
    control = MissionControl("kill-mission")
    monkeypatch.setitem(api._pentest_tasks, "kill-task", {
        "state_file": str(state_path),
        "status": "running",
        "control": control,
    })

    result = asyncio.run(api.pentest_set_kill_switch(api.KillSwitchRequest(reason="fixture emergency")))
    assert result["enabled"] is True
    assert result["affected_tasks"] == ["kill-task"]
    assert control.is_cancel_requested
    assert policy.emergency_stop_enabled()
    reloaded = State(str(state_path))
    assert reloaded.data["global_kill_switch"]["enabled"] is True
    assert any(event.event_type == "system.kill_switch.changed" for event in reloaded.event_store.read())

    disabled = asyncio.run(api.pentest_set_kill_switch(api.KillSwitchRequest(enabled=False, reason="fixture reset")))
    assert disabled["enabled"] is False
    assert not policy.emergency_stop_enabled()
