from __future__ import annotations

import asyncio

import pytest

from app.core.evaluation import (
    BenchmarkCase,
    BenchmarkManifest,
    BenchmarkReport,
    BenchmarkRunner,
    CaseResult,
    ModelReplacementGate,
)
from app.core.model_gateway import ModelGateway, ModelRouter
from app.core.resource_budget import BudgetExceeded, BudgetLimits, BudgetManager
from app.services.pentest_agent.state import State


def test_router_prefers_rules_for_low_value_and_strong_for_planning():
    router = ModelRouter()
    low = router.choose(task_kind="classification", task_value=0.1, complexity=0.1, risk="low")
    high = router.choose(task_kind="planning", task_value=0.4, complexity=0.4, risk="medium")
    assert low.strategy == "rule"
    assert high.strategy == "strong"
    assert low.route_id == router.choose(
        task_kind="classification", task_value=0.1, complexity=0.1, risk="low"
    ).route_id


def test_gateway_records_route_and_passes_it_to_route_aware_provider():
    received = []

    def provider(system, user, route):
        received.append(route)
        return '{"status":"ok"}'

    gateway = ModelGateway(
        provider,
        router=ModelRouter(),
        budget=BudgetManager(BudgetLimits(llm_tokens=10_000)),
        task_id="route-task",
    )
    result = asyncio.run(
        gateway.complete_json(
            "system",
            "classify fixture",
            dict[str, str],
            routing_context={
                "task_kind": "classification",
                "task_value": 0.1,
                "complexity": 0.1,
                "risk": "low",
            },
        )
    )
    assert result == {"status": "ok"}
    assert received and received[0].strategy == "rule"
    manifest = gateway.audit_manifest()
    assert manifest[0]["route_strategy"] == "rule"
    assert manifest[0]["route_id"]
    assert manifest[0]["choice_reason"]
    assert manifest[0]["model"] == "deterministic-rules"


def test_gateway_route_budget_is_enforced_before_provider_call():
    called = []

    def provider(system, user):
        called.append(True)
        return "ok"

    gateway = ModelGateway(
        provider,
        router=ModelRouter(strong_max_tokens=4096),
        budget=BudgetManager(BudgetLimits(llm_tokens=20)),
        task_id="tiny-budget",
    )
    with pytest.raises(BudgetExceeded):
        asyncio.run(
            gateway.complete(
                "system text",
                "user text",
                routing_context={"task_kind": "planning", "task_value": 1.0, "complexity": 1.0},
            )
        )
    assert not called
    assert gateway.audit_manifest()[0]["status"] == "budget_exhausted"


def test_gateway_can_write_route_audit_into_task_state(tmp_path):
    state = State(str(tmp_path / "state.json"))
    gateway = ModelGateway(
        lambda system, user: "ok",
        task_id="task-model-audit",
        router=ModelRouter(),
        audit_sink=state.record_model_call,
    )
    asyncio.run(
        gateway.complete(
            "system",
            "fixture",
            routing_context={"task_kind": "classification", "task_value": 0.1, "complexity": 0.1},
        )
    )
    assert state.data["model_calls"][0]["route_strategy"] == "rule"
    assert any(event.event_type == "model.called" for event in state.event_store.read())


def test_model_replacement_gate_uses_same_manifest_and_repetitions():
    manifest = BenchmarkManifest(
        "benchmark.v1",
        (BenchmarkCase("case", "known_linux", "VULNERABILITY_CONFIRMED", "TARGET"),),
    )

    def execute(_case):
        return {"status": "VULNERABILITY_CONFIRMED", "cost": 1.0}

    baseline = BenchmarkRunner(execute).run(manifest, repetitions=3)
    candidate = BenchmarkRunner(execute).run(manifest, repetitions=3)
    passed, failures = ModelReplacementGate().check(baseline, candidate)
    assert passed, failures

    regression = BenchmarkReport("benchmark.v1", 3, [
        CaseResult("case", "known_linux", "VULNERABILITY_CONFIRMED", "INCONCLUSIVE", 0.1)
        for _ in range(3)
    ])
    passed, failures = ModelReplacementGate().check(baseline, regression)
    assert not passed
    assert failures
