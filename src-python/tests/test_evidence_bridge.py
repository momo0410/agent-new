from __future__ import annotations

from app.core.contracts import EvidenceStatus
from app.core.evidence_bridge import EvidenceBridge
from app.services.pentest_agent.state import State


def test_bridge_creates_typed_port_evidence_and_event(tmp_path):
    state = State(str(tmp_path / "task.json"))
    state.add_target("TARGET")
    bridge = EvidenceBridge()
    result = bridge.ingest(
        task_id="task",
        target="TARGET",
        action_id="action-1",
        tool="scanner",
        action_type="recon",
        result={"returncode": 0, "parsed": [{"port": 80, "state": "open"}]},
        raw_output="80/tcp open",
    )
    assert result.evidence.status == EvidenceStatus.DISCOVERED
    bridge.persist(state, result)
    assert state.data["canonical_evidence"][0]["evidence_id"] == result.evidence.evidence_id
    assert any(item.event_type == "evidence.recorded" for item in state.event_store.read())


def test_bridge_does_not_promote_session_text_without_strict_proof():
    result = EvidenceBridge().ingest(
        task_id="task",
        target="TARGET",
        action_id="action-2",
        tool="shell",
        action_type="session_verify",
        result={"stdout": "session established; uid=1000"},
        raw_output="session established; uid=1000",
    )
    assert result.evidence.status == EvidenceStatus.INCONCLUSIVE
    assert result.finding is None


def test_bridge_marks_policy_and_cancellation_as_terminal_observations():
    bridge = EvidenceBridge()
    blocked = bridge.ingest(
        task_id="task",
        target="TARGET",
        action_id="action-3",
        tool="probe",
        result={"policy_blocked": True, "status": "blocked"},
    )
    cancelled = bridge.ingest(
        task_id="task",
        target="TARGET",
        action_id="action-4",
        tool="probe",
        result={"cancelled": True, "status": "cancelled"},
    )
    assert blocked.evidence.status == EvidenceStatus.BLOCKED_BY_POLICY
    assert cancelled.evidence.status == EvidenceStatus.CANCELLED
