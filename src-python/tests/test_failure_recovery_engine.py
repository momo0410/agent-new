from app.core.failure_recovery import FailureClassifier, FailureRecoveryEngine, FailureType, RecoveryPlanner


def test_failure_classification_carries_event_and_evidence_references():
    result = {
        "tool": "TARGET_TOOL",
        "action_id": "action-1",
        "event_id": "event-1",
        "evidence_refs": ["evidence-1"],
        "error": "connection refused",
    }
    classification = FailureClassifier().classify(result)
    assert classification.failure_type == FailureType.NETWORK
    assert set(classification.evidence_refs) >= {"action-1", "event-1", "evidence-1"}
    plans = RecoveryPlanner().propose(classification, equivalent_tools=["TARGET_TOOL_ALT"])
    assert all("evidence_refs" in item for item in plans)
    assert any(item["strategy"] == "equivalent_tool" for item in plans)


def test_recovery_engine_stops_unchanged_retries():
    engine = FailureRecoveryEngine(max_same_action=2)
    result = {"tool": "TARGET_TOOL", "target": "TARGET", "args": "--same", "error": "timeout"}
    first = engine.decide(result)
    second = engine.decide(result)
    third = engine.decide(result)
    assert first["attempt_count"] == 1
    assert second["attempt_count"] == 2
    assert third["attempt_count"] == 3
    assert third["stopped"] is True
    assert third["plans"] == [{
        "strategy": "stop",
        "reason": "unchanged action retry cap reached",
        "do_not_repeat": ["same normalized action without new evidence"],
        "evidence_refs": [],
    }]
