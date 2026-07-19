from __future__ import annotations

from app.core.task_store import EventSourcedTaskStore


def test_task_projectors_fold_observation_control_and_model_events(tmp_path):
    store = EventSourcedTaskStore(tmp_path / "events.jsonl")
    store.create("task-projector", {"scope_id": "scope-1"})
    store.events.append(
        "task-projector",
        "observation.recorded",
        {"observation_id": "obs-1", "raw_hash": "a" * 64, "parser_version": "p.v1"},
    )
    store.events.append(
        "task-projector",
        "autonomy.blocked",
        {"action_id": "a1", "reason": "approval required"},
    )
    store.events.append(
        "task-projector",
        "action_limit.changed",
        {"previous": "post_verify", "current": "probe"},
        previous_state="post_verify",
        new_state="probe",
        reason="course step",
    )
    store.events.append(
        "task-projector",
        "action_limit.blocked",
        {"action_id": "a2", "limit": "probe"},
    )
    store.events.append("task-projector", "model.called", {"call_id": "model-1", "route_strategy": "rule"})
    store.events.append(
        "task-projector",
        "asset.inventory.imported",
        {"import_id": "asset-import-1", "source_records": 2},
    )
    store.events.append(
        "task-projector",
        "runtime.snapshot",
        {"snapshot_hash": "runtime-hash", "tool_count": 3},
    )
    state = store.rebuild()
    assert state["observations"]["obs-1"]["parser_version"] == "p.v1"
    assert state["autonomy_blocks"][0]["action_id"] == "a1"
    assert state["action_limit"] == "probe"
    assert state["action_limit_blocks"][0]["action_id"] == "a2"
    assert state["model_calls"][0]["route_strategy"] == "rule"
    assert state["asset_imports"][0]["import_id"] == "asset-import-1"
    assert state["runtime_snapshot"]["snapshot_hash"] == "runtime-hash"
