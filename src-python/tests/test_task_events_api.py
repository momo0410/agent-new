from __future__ import annotations

import asyncio

from app.routers import api
from app.core.planner_contracts import ActionLimitController, AutonomyController
from app.services.pentest_agent.state import State


def test_task_events_endpoint_returns_verified_contiguous_pages(monkeypatch, tmp_path):
    state_path = tmp_path / "pentest_state_task-events.json"
    state = State(str(state_path))
    state.event_store.append(
        state.event_task_id,
        "scope.created",
        {"scope_id": "scope-events"},
        idempotency_key="scope:events",
    )
    state.event_store.append(
        state.event_task_id,
        "mission.paused",
        {"mission_id": "mission-events", "reason": "operator"},
        new_state="PAUSED",
        reason="operator",
        idempotency_key="mission:events:paused",
    )
    monkeypatch.setitem(api._pentest_tasks, "task-events", {"state_file": str(state_path)})

    first = asyncio.run(api.pentest_get_events("task-events", after_sequence=0, limit=1))
    assert [item["sequence"] for item in first["events"]] == [1]
    assert first["has_more"] is True
    assert first["last_hash"]

    second = asyncio.run(
        api.pentest_get_events("task-events", after_sequence=first["next_sequence"], limit=10)
    )
    assert [item["sequence"] for item in second["events"]] == [2]
    assert second["events"][0]["event_type"] == "mission.paused"
    assert second["has_more"] is False


def test_autonomy_endpoint_persists_transition_event(monkeypatch, tmp_path):
    state_path = tmp_path / "pentest_state_task-autonomy.json"
    state = State(str(state_path))
    state.data["autonomy_mode"] = "supervised"
    state.save()
    monkeypatch.setitem(
        api._pentest_tasks,
        "task-autonomy",
        {"state_file": str(state_path), "autonomy": AutonomyController("supervised")},
    )
    response = asyncio.run(
        api.pentest_set_autonomy(
            api.AutonomyModeRequest(
                task_id="task-autonomy",
                mode="advisory",
                actor="teacher",
                reason="class demonstration",
            )
        )
    )
    assert response["autonomy_mode"] == "advisory"
    reloaded = State(str(state_path))
    assert reloaded.data["autonomy_history"][-1]["actor"] == "teacher"
    assert any(event.event_type == "autonomy.changed" for event in reloaded.event_store.read())


def test_action_limit_endpoint_updates_live_controller_and_event(monkeypatch, tmp_path):
    state_path = tmp_path / "pentest_state_task-action-limit.json"
    state = State(str(state_path))
    state.data["action_limit"] = "post_verify"
    state.save()
    controller = ActionLimitController("post_verify")
    monkeypatch.setitem(
        api._pentest_tasks,
        "task-action-limit",
        {"state_file": str(state_path), "action_limit": controller},
    )
    response = asyncio.run(
        api.pentest_set_action_limit(
            api.ActionLimitRequest(
                task_id="task-action-limit",
                level="probe",
                actor="teacher",
                reason="class observation only",
            )
        )
    )
    assert response["action_limit"] == "probe"
    assert controller.level == "probe"
    reloaded = State(str(state_path))
    assert reloaded.data["action_limit_history"][-1]["actor"] == "teacher"
    assert any(event.event_type == "action_limit.changed" for event in reloaded.event_store.read())
