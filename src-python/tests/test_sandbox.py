from __future__ import annotations

from app.core.sandbox import GeneratedCodeSandbox, SandboxPolicy


def test_generated_code_sandbox_runs_json_fixture_and_records_environment():
    sandbox = GeneratedCodeSandbox(SandboxPolicy(timeout_seconds=5))
    result = sandbox.run("RESULT = {'value': INPUT['value'] + 1}", {"value": 4})
    assert result.status == "completed"
    assert result.output == {"value": 5}
    assert result.environment_fingerprint["schema_version"] == "environment.v1"
    assert result.code_hash


def test_generated_code_sandbox_blocks_network_and_simulates_without_launch():
    sandbox = GeneratedCodeSandbox()
    blocked = sandbox.run("import socket\nRESULT = {}")
    assert blocked.status == "blocked"
    assert blocked.findings
    simulated = sandbox.run("RESULT = {'ignored': True}", dry_run=True, simulated_result={"status": "fixture"})
    assert simulated.status == "simulated"
    assert simulated.output["status"] == "fixture"


def test_generated_code_sandbox_times_out_and_does_not_allow_path_escape():
    sandbox = GeneratedCodeSandbox(SandboxPolicy(timeout_seconds=0.2))
    timeout = sandbox.run("while True:\n    pass")
    assert timeout.status in {"timeout", "failed"}
    blocked = sandbox.run("RESULT = open('/etc/passwd').read()")
    assert blocked.status == "blocked"


def test_state_snapshot_contains_runtime_fingerprint(tmp_path):
    from app.services.pentest_agent.state import State

    state = State(str(tmp_path / "state.json"))
    assert state.data["environment_fingerprint"]["schema_version"] == "environment.v1"
    assert state.data["environment_fingerprint"]["python"]


def test_state_runtime_snapshot_captures_tool_versions(tmp_path):
    from app.services.pentest_agent.state import State

    state = State(str(tmp_path / "runtime.json"))
    state.record_tool_coverage_gaps({
        "generated_at": "fixture-time",
        "summary": {"ok": 1, "warn": 0, "error": 0, "total": 1},
        "tools": [{
            "tool": "fixture-tool",
            "status": "ok",
            "binary": "fixture-tool",
            "binary_path": "C:/fixture/fixture-tool",
            "version": "1.2.3",
            "help_probe_ok": True,
        }],
    })
    snapshot = state.data["runtime_snapshot"]
    assert snapshot["tools"]["fixture-tool"]["version"] == "1.2.3"
    assert len(snapshot["snapshot_hash"]) == 64
    assert state.data["versions"]["tools"]["fixture-tool"] == "1.2.3"
