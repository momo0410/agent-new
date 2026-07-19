from datetime import datetime, timedelta, timezone

from app.core.contracts import ScopeContract
from app.core.planner_contracts import ActionLimitController, AutonomyController
from app.core.scope_policy import ScopePolicy
from app.services.pentest_agent import executor as executor_module
from app.services.pentest_agent.executor import Executor
from app.services.pentest_agent.state import State


def test_executor_observes_live_autonomy_changes(monkeypatch, tmp_path):
    registry = {
        "fixture-tool": {
            "name": "fixture-tool",
            "command": "echo {args}",
            "timeout": 5,
            "parser": "",
            "risk": "high",
            "requires": [],
            "source": "static",
        }
    }
    monkeypatch.setattr(executor_module, "build_tool_registry", lambda tools_config=None: registry)
    state = State(str(tmp_path / "autonomy-state.json"))
    state.data["targets"] = ["TARGET"]
    scope = ScopeContract(
        owner="fixture",
        allowed_targets=["TARGET"],
        allowed_ports=[80],
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        autonomy_mode="advisory",
    )
    policy = ScopePolicy(b"a" * 32)
    controller = AutonomyController("advisory")
    executor = Executor(
        state=state,
        scope_contract=scope,
        scope_token=policy.issue_token(scope),
        scope_policy=policy,
        task_id="autonomy-task",
        autonomy_controller=controller,
    )
    monkeypatch.setattr(
        executor,
        "_ensure_tool_probe",
        lambda tool_name, cfg, refresh=False: {
            "tool": tool_name,
            "missing_requires": [],
            "binary": "echo",
            "binary_path": "echo",
            "help_probe_ok": True,
            "help_options": set(),
            "version": "fixture",
        },
    )

    advisory = executor.run(
        "fixture-tool", "TARGET", dry_run=True, action_type="exploit", target="TARGET", port=80
    )
    assert advisory["autonomy_blocked"] is True
    assert advisory["autonomy_mode"] == "advisory"

    controller.set_mode("supervised", actor="operator", reason="review")
    supervised = executor.run(
        "fixture-tool", "TARGET", dry_run=True, action_type="exploit", target="TARGET", port=80
    )
    assert supervised["autonomy_blocked"] is True

    approved = executor.run(
        "fixture-tool",
        "TARGET",
        dry_run=True,
        action_type="exploit",
        target="TARGET",
        port=80,
        autonomy_approved=True,
    )
    assert approved["dry_run"] is True

    controller.set_mode("unattended", actor="operator", reason="fixture run")
    unattended = executor.run(
        "fixture-tool", "TARGET", dry_run=True, action_type="exploit", target="TARGET", port=80
    )
    assert unattended["dry_run"] is True
    assert any(event.event_type == "autonomy.blocked" for event in state.event_store.read())


def test_executor_observes_live_action_limit(monkeypatch, tmp_path):
    registry = {
        "fixture-tool": {
            "name": "fixture-tool", "command": "echo {args}", "timeout": 5,
            "parser": "", "risk": "high", "requires": [], "source": "static",
        }
    }
    monkeypatch.setattr(executor_module, "build_tool_registry", lambda tools_config=None: registry)
    state = State(str(tmp_path / "limit-state.json"))
    state.data["targets"] = ["TARGET"]
    scope = ScopeContract(
        owner="fixture", allowed_targets=["TARGET"], allowed_ports=[80],
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5), autonomy_mode="unattended",
    )
    policy = ScopePolicy(b"b" * 32)
    limit = ActionLimitController("probe")
    executor = Executor(
        state=state,
        scope_contract=scope,
        scope_token=policy.issue_token(scope),
        scope_policy=policy,
        task_id="limit-task",
        autonomy_controller=AutonomyController("unattended"),
        action_limit_controller=limit,
    )
    blocked = executor.run(
        "fixture-tool", "TARGET", dry_run=True, action_type="exploit", target="TARGET", port=80
    )
    assert blocked["action_limit_blocked"] is True
    limit.set_limit("post_verify", actor="operator", reason="fixture")
    monkeypatch.setattr(
        executor,
        "_ensure_tool_probe",
        lambda tool_name, cfg, refresh=False: {
            "tool": tool_name, "missing_requires": [], "binary": "echo", "binary_path": "echo",
            "help_probe_ok": True, "help_options": set(), "version": "fixture",
        },
    )
    allowed = executor.run(
        "fixture-tool", "TARGET", dry_run=True, action_type="exploit", target="TARGET", port=80
    )
    assert allowed["dry_run"] is True
    assert any(event.event_type == "action_limit.blocked" for event in state.event_store.read())
