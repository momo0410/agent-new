from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("pytest_benchmark")

from app.core.contracts import ActionEnvelope, ActionLevel, ScopeContract
from app.core.scope_policy import ScopePolicy


def test_benchmark_scope_authorization(benchmark):
    scope = ScopeContract(
        owner="benchmark",
        allowed_targets=["TARGET"],
        allowed_ports=[80],
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    policy = ScopePolicy(b"benchmark-secret" * 2)
    token = policy.issue_token(scope)
    envelope = ActionEnvelope(
        task_id="benchmark",
        scope_id=scope.scope_id,
        target="TARGET",
        port=80,
        plugin="probe",
        action_level=ActionLevel.PROBE,
        intent="benchmark",
        expected_evidence=["banner"],
    )
    result = benchmark(policy.authorize_action, envelope, scope, token)
    assert result.allowed
