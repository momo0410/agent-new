from __future__ import annotations

from app.core.audit_log import AuditLog


def test_audit_levels_are_chained_and_role_filtered(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.append("task.started", {"task_id": "task-1"}, level="user_visible")
    log.append("planner.debug", {"candidate_count": 2}, level="debug")
    log.append("scope.denied", {"reason": "outside"}, level="security_audit")
    log.append("credential.observed", {"password": "fixture-secret"}, level="sensitive_evidence")
    assert log.read(verify=True)[-1]["sequence"] == 4
    assert len(log.read_for("student")) == 1
    assert len(log.read_for("teacher")) == 3
    assert len(log.read_for("security_admin")) == 4

    sensitive = log.read_level("sensitive_evidence")[0]
    assert sensitive["payload"]["password"]["redacted"] is True
    assert "fixture-secret" not in str(sensitive)


def test_unknown_role_has_no_audit_visibility(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.append("event", {}, level="user_visible")
    assert log.read_for("unknown-role") == []
