from datetime import datetime, timedelta, timezone

import pytest

from app.core.asset_graph import AssetGraph
from app.core.contracts import ActionEnvelope, ActionLevel, EvidenceStatus, ScopeContract
from app.core.done_gate import DoneGate
from app.core.event_store import EventStore, EventStoreCorruption
from app.core.evidence import EvidenceStateMachine, judge_privilege_evidence, judge_session_evidence, raw_hash
from app.core.scope_policy import ScopePolicy
from app.core.session_manager import SessionManager
from app.services.pentest_agent.executor import Executor
from app.services.pentest_agent.state import State


def future():
    return datetime.now(timezone.utc) + timedelta(minutes=15)


def make_scope():
    return ScopeContract(
        owner="teacher",
        allowed_targets=["TARGET"],
        allowed_ports=[80, 443],
        expires_at=future(),
    )


def make_action(scope_id: str, target: str = "TARGET", port: int = 80, level: ActionLevel = ActionLevel.PROBE):
    return ActionEnvelope(
        task_id="task-1",
        scope_id=scope_id,
        target=target,
        port=port,
        plugin="http_probe",
        action_level=level,
        intent="collect banner evidence",
        expected_evidence=["http status"],
    )


def test_scope_token_authorizes_in_scope_action_and_denies_out_of_scope():
    scope = make_scope()
    policy = ScopePolicy(b"unit-test-secret" * 2)
    token = policy.issue_token(scope)
    assert policy.authorize_action(make_action(scope.scope_id), scope, token).allowed
    denied = policy.authorize_action(make_action(scope.scope_id, target="OTHER"), scope, token)
    assert not denied.allowed
    assert denied["reason"] == "target is outside scope"


def test_scope_policy_rejects_prohibited_action():
    scope = make_scope()
    policy = ScopePolicy(b"unit-test-secret" * 2)
    token = policy.issue_token(scope)
    decision = policy.authorize_action(make_action(scope.scope_id, level=ActionLevel.PROHIBITED), scope, token)
    assert not decision.allowed


def test_executor_enforces_scope_before_tool_dispatch(tmp_path):
    scope = make_scope()
    policy = ScopePolicy(b"unit-test-secret" * 2)
    token = policy.issue_token(scope)
    state = State(str(tmp_path / "state.json"))
    state.add_target("TARGET")
    executor = Executor(
        state=state,
        scope_contract=scope,
        scope_token=token,
        scope_policy=policy,
        task_id="task-1",
    )
    result = executor.run("nmap", "-p 81 TARGET", dry_run=True, action_type="scan", target="TARGET", port=81)
    assert result["policy_blocked"] is True
    assert result["policy_decision"]["reason"] == "port is outside scope"
    assert any(event.event_type == "policy.denied" for event in state.event_store.read())


def test_nmap_parser_recognizes_http_when_service_probe_reports_unknown():
    raw = (
        "3000/tcp open  ppp?\n"
        "SF-Port3000-TCP:V=7.98%r(GetRequest,HTTP/1.1\\x20200\\x20OK"
        "\\r\\nContent-Type:\\x20text/html)\n"
        "Nmap done: 1 IP address (1 host up) scanned"
    )
    parsed = Executor().parse_port_services(raw)
    assert parsed == [{"port": 3000, "state": "open", "service": "http (HTTP response detected)"}]


def test_event_store_is_hash_chained_and_detects_tampering(tmp_path):
    store = EventStore(tmp_path / "events.jsonl")
    store.append("task-1", "task.created", {"target": "TARGET"})
    store.append("task-1", "action.started", {"tool": "probe"})
    assert store.verify()["event_count"] == 2
    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace("action.started", "action.finished")
    (tmp_path / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(EventStoreCorruption):
        store.read()


def test_evidence_state_machine_requires_evidence_for_verified_state():
    from app.core.contracts import EvidenceRecord, FindingRecord

    finding = FindingRecord(task_id="task-1", title="example", target="TARGET")
    finding = EvidenceStateMachine().transition(finding, EvidenceStatus.DISCOVERED)
    finding = EvidenceStateMachine().transition(finding, EvidenceStatus.CANDIDATE)
    with pytest.raises(ValueError):
        EvidenceStateMachine().transition(finding, EvidenceStatus.VERIFIED_VULNERABLE)
    evidence = EvidenceRecord(
        task_id="task-1",
        target="TARGET",
        evidence_type="reproduction",
        status=EvidenceStatus.VERIFIED_VULNERABLE,
        rule_id="test.rule.v1",
        raw_hash=raw_hash("proof"),
    )
    verified = EvidenceStateMachine().transition(finding, EvidenceStatus.ATTEMPTED)
    verified = EvidenceStateMachine().transition(verified, EvidenceStatus.VERIFIED_VULNERABLE, evidence=evidence)
    assert verified.status == EvidenceStatus.VERIFIED_VULNERABLE
    assert evidence.evidence_id in verified.evidence_ids


def test_session_judge_requires_binding_challenge_and_identity():
    failed = judge_session_evidence(target="TARGET", observed_target="OTHER", challenge="c", output="c", identity="uid=0")
    assert not failed.accepted
    failed = judge_session_evidence(target="TARGET", observed_target="TARGET", challenge="c", output="", identity="uid=0")
    assert not failed.accepted
    ok = judge_session_evidence(target="TARGET", observed_target="TARGET", challenge="c", output="c uid=1000", identity="uid=1000")
    assert ok.accepted and ok.status == EvidenceStatus.SESSION_ESTABLISHED
    assert judge_privilege_evidence(session_verified=True, identity_output="uid=0(root)").accepted


def test_session_manager_expires_and_binds_to_task():
    manager = SessionManager(default_ttl_seconds=60)
    session = manager.create(task_id="task-1", target="TARGET", transport="shell", owner="teacher")
    wrong = manager.verify(session.session_id, task_id="task-2", target="TARGET", output=session.challenge, identity="uid=1000")
    assert not wrong.valid
    verified = manager.verify(session.session_id, task_id="task-1", target="TARGET", output=session.challenge, identity="uid=1000")
    assert verified.valid
    assert manager.heartbeat(session.session_id, output=session.challenge)
    assert manager.close(session.session_id)
    assert manager.get(session.session_id) is None


def test_done_gate_blocks_unresolved_high_value_surface():
    gate = DoneGate(must_try_score=50)
    blocked = gate.evaluate([{"surface_id": "TARGET|80", "score": 90, "status": "attempted"}], report_complete=True)
    assert not blocked.can_close
    closed = gate.evaluate([{"surface_id": "TARGET|80", "score": 90, "status": "exhausted"}], report_complete=True)
    assert closed.can_close


def test_asset_graph_rebuilds_services_and_prioritizes_must_try_queue():
    graph = AssetGraph.from_state({
        "targets": ["TARGET"],
        "findings": [{"ip": "TARGET", "port": 443, "service": "https", "score": 80}],
        "attack_surfaces": [{"surface_id": "TARGET|22", "last_tool": "ssh", "score": 90, "status": "attempted"}],
    })
    assert {node.node_id for node in graph.nodes} >= {"target:TARGET", "service:TARGET|443", "service:TARGET|22"}
    assert graph.must_try_queue()[0].node_id == "service:TARGET|22"
    assert len(graph.edges) == 2


def test_state_writes_redacted_events(tmp_path):
    state = State(str(tmp_path / "state.json"))
    state.add_target("TARGET")
    state.add_finding({"ip": "TARGET", "port": 80, "service": "http"})
    action = state.start_action("curl", "http://TARGET", llm_decision="probe", ports=[80])
    state.finish_action(action, result_summary="200 OK", full_stdout="password=SECRET", returncode=0)
    events = state.event_store.read()
    assert events
    rendered = (tmp_path / "state.json.events.jsonl").read_text(encoding="utf-8")
    assert "SECRET" not in rendered
    assert any(event.event_type == "action.finished" for event in events)


def test_report_view_contains_fact_first_teaching_sections(tmp_path):
    state = State(str(tmp_path / "state.json"))
    state.add_target("TARGET")
    state.add_finding({"ip": "TARGET", "port": 80, "service": "http"})
    view = state.build_report_view_model()
    assert {"facts", "inferences", "attack_path", "failure_path", "defense_view"} <= set(view["teaching"])
    assert view["asset_graph"]["schema_version"] == "asset-graph.v1"
    assert view["teaching"]["facts"]
