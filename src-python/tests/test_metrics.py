from __future__ import annotations

from app.core.metrics import MetricsAggregator, RuntimeHealthMonitor
from app.services.pentest_agent.state import State


def test_metrics_aggregate_across_required_dimensions():
    metrics = MetricsAggregator()
    metrics.record_action({
        "status": "completed",
        "tool": "probe",
        "target": "TARGET",
        "skill_id": "skill-1",
        "model": "model-1",
        "tool_version": "1.0",
        "duration_seconds": 0.2,
        "cost": 3,
    }, task_id="task-1")
    metrics.record_events([{
        "event_type": "policy.denied",
        "payload": {"target": "TARGET", "plugin": "probe"},
    }], task_id="task-1")
    snapshot = metrics.snapshot(group_by=["task_id", "plugin"])
    group = next(iter(snapshot["groups"].values()))
    assert group["runs"] == 2
    assert group["security_events"] == 1
    assert group["success_rate"] == 0.5


def test_runtime_health_monitor_quarantines_on_orphan_or_budget_signal(tmp_path):
    file_path = tmp_path / "events.log"
    file_path.write_text("x", encoding="utf-8")
    monitor = RuntimeHealthMonitor(disk_paths=[file_path])
    file_path.write_text("x" * 10, encoding="utf-8")
    health = monitor.inspect(process_count=1, budget_usage={"commands": 2}, budget_limits={"commands": 1})
    assert health["quarantine"] is True
    assert {item["kind"] for item in health["alerts"]} >= {"process", "budget", "disk"}


def test_state_exposes_dimensioned_metrics(tmp_path):
    state = State(str(tmp_path / "state.json"))
    state.log_action("probe", "TARGET", result_summary="ok")
    snapshot = state.metrics_snapshot(group_by=["task_id", "plugin"])
    assert snapshot["groups"]
    assert "task_id" in snapshot["dimensions"]
