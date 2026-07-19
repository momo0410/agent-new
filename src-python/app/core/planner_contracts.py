"""Explainable planner contracts and anti-stagnation primitives."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .contracts import AutonomyMode


@dataclass(frozen=True)
class CandidateAction:
    action_id: str
    target: str
    asset_id: str
    action: str
    action_level: str
    preconditions: tuple[str, ...]
    expected_evidence: tuple[str, ...]
    failure_branches: tuple[dict[str, Any], ...] = ()
    risk: str = "low"
    estimated_cost: float = 0.0
    information_gain: float = 0.0
    success_probability: float = 0.0
    impact: float = 0.0
    tool_health: float = 1.0
    repetition_penalty: float = 0.0
    scope_fit: float = 1.0
    source_refs: tuple[str, ...] = ()
    must_try: bool = False
    must_not_try: bool = False
    stop_conditions: tuple[str, ...] = ()
    idempotency_key: str = ""
    score: float = 0.0
    score_factors: dict[str, float] = field(default_factory=dict)
    exclusive_resources: tuple[str, ...] = ()
    parallel_safe: bool = True

    def __post_init__(self) -> None:
        if not self.idempotency_key:
            value = f"{self.target}|{self.asset_id}|{self.action}|{self.action_level}"
            object.__setattr__(self, "idempotency_key", hashlib.sha256(value.encode()).hexdigest()[:32])

    def as_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "target": self.target,
            "asset_id": self.asset_id,
            "action": self.action,
            "action_level": self.action_level,
            "preconditions": list(self.preconditions),
            "expected_evidence": list(self.expected_evidence),
            "failure_branches": [dict(item) for item in self.failure_branches],
            "risk": self.risk,
            "estimated_cost": self.estimated_cost,
            "information_gain": self.information_gain,
            "success_probability": self.success_probability,
            "impact": self.impact,
            "tool_health": self.tool_health,
            "repetition_penalty": self.repetition_penalty,
            "scope_fit": self.scope_fit,
            "source_refs": list(self.source_refs),
            "must_try": self.must_try,
            "must_not_try": self.must_not_try,
            "stop_conditions": list(self.stop_conditions),
            "idempotency_key": self.idempotency_key,
            "score": self.score,
            "score_factors": dict(self.score_factors),
            "exclusive_resources": list(self.exclusive_resources),
            "parallel_safe": self.parallel_safe,
        }


class CandidateScorer:
    """Weighted, inspectable scoring.  Weights are config, not hidden prompt text."""

    DEFAULT_WEIGHTS = {
        "success_probability": 0.30,
        "information_gain": 0.22,
        "impact": 0.16,
        "tool_health": 0.10,
        "scope_fit": 0.12,
        "repetition_penalty": -0.15,
        "estimated_cost": -0.08,
    }

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = dict(self.DEFAULT_WEIGHTS)
        self.weights.update(weights or {})

    def score(self, candidate: CandidateAction) -> CandidateAction:
        factors = {
            "success_probability": max(0.0, min(1.0, candidate.success_probability)),
            "information_gain": max(0.0, min(1.0, candidate.information_gain)),
            "impact": max(0.0, min(1.0, candidate.impact)),
            "tool_health": max(0.0, min(1.0, candidate.tool_health)),
            "scope_fit": max(0.0, min(1.0, candidate.scope_fit)),
            "repetition_penalty": max(0.0, min(1.0, candidate.repetition_penalty)),
            "estimated_cost": max(0.0, min(1.0, candidate.estimated_cost)),
        }
        value = sum(self.weights.get(key, 0.0) * number for key, number in factors.items())
        if candidate.must_try:
            value += 0.15
        if candidate.must_not_try:
            value = float("-inf")
        return CandidateAction(**{**candidate.__dict__, "score": round(value, 6), "score_factors": factors})

    def rank(self, candidates: Iterable[CandidateAction]) -> list[CandidateAction]:
        return sorted((self.score(item) for item in candidates), key=lambda item: (-item.score, item.action_id))


@dataclass(frozen=True)
class PlanValidationResult:
    valid: bool
    reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "reasons": list(self.reasons)}


class PlanValidator:
    """Execution boundary for planner output.

    A candidate can be displayed while incomplete, but execution requires an
    explicit evidence rule and a stopping condition.  This keeps model output
    in the proposal layer until the contract is complete.
    """

    def validate_candidate(self, candidate: CandidateAction) -> PlanValidationResult:
        reasons: list[str] = []
        if not str(candidate.target).strip():
            reasons.append("target is required")
        if not str(candidate.action).strip():
            reasons.append("action is required")
        if not candidate.expected_evidence:
            reasons.append("expected evidence is required")
        if not candidate.stop_conditions:
            reasons.append("stop condition is required")
        if not candidate.source_refs:
            reasons.append("at least one source reference is required")
        if candidate.must_try and candidate.must_not_try:
            reasons.append("candidate cannot be both must_try and must_not_try")
        return PlanValidationResult(not reasons, tuple(dict.fromkeys(reasons)))

    def validate_graph(self, graph: PlanGraph) -> PlanValidationResult:
        reasons = list(graph.validate())
        for candidate in graph.nodes.values():
            result = self.validate_candidate(candidate)
            reasons.extend(f"{candidate.action_id}: {reason}" for reason in result.reasons)
        return PlanValidationResult(not reasons, tuple(dict.fromkeys(reasons)))


@dataclass(frozen=True)
class AutonomyTransition:
    previous: AutonomyMode
    current: AutonomyMode
    actor: str
    reason: str


class AutonomyController:
    """Task-local autonomy state with an auditable transition history."""

    def __init__(self, mode: AutonomyMode | str = AutonomyMode.SUPERVISED):
        self._mode = mode if isinstance(mode, AutonomyMode) else AutonomyMode(str(mode).lower())
        self._history: list[AutonomyTransition] = []

    @property
    def mode(self) -> AutonomyMode:
        return self._mode

    def set_mode(self, mode: AutonomyMode | str, *, actor: str, reason: str) -> AutonomyTransition:
        requested = mode if isinstance(mode, AutonomyMode) else AutonomyMode(str(mode).lower())
        transition = AutonomyTransition(self._mode, requested, str(actor)[:160], str(reason)[:500])
        self._mode = requested
        self._history.append(transition)
        return transition

    def can_execute(
        self,
        candidate: CandidateAction,
        *,
        approved: bool = False,
        experimental: bool = False,
    ) -> tuple[bool, str]:
        if candidate.must_not_try:
            return False, "candidate is explicitly disabled"
        if not candidate.expected_evidence:
            return False, "candidate has no expected evidence"
        if self._mode == AutonomyMode.ADVISORY:
            return False, "advisory mode only proposes actions"
        if self._mode == AutonomyMode.SUPERVISED and not approved and str(candidate.risk).lower() in {"high", "critical"}:
            return False, "high-risk action requires supervision approval"
        if self._mode == AutonomyMode.UNATTENDED and experimental:
            return False, "experimental action is disabled in unattended mode"
        return True, "autonomy policy permits execution"

    def history(self) -> list[dict[str, str]]:
        return [
            {
                "previous": item.previous.value,
                "current": item.current.value,
                "actor": item.actor,
                "reason": item.reason,
            }
            for item in self._history
        ]


@dataclass(frozen=True)
class ActionLimitTransition:
    previous: str
    current: str
    actor: str
    reason: str


class ActionLimitController:
    """Live task ceiling used to freeze actions above an operator-selected level."""

    ORDER = (
        "observe", "probe", "credential_test", "exploit", "session_verify",
        "post_verify",
    )

    def __init__(self, level: str = "post_verify") -> None:
        self._level = self._validate(level)
        self._history: list[ActionLimitTransition] = []

    @classmethod
    def _validate(cls, level: str) -> str:
        value = str(level or "").strip().lower()
        if value not in cls.ORDER:
            raise ValueError("action limit is invalid")
        return value

    @property
    def level(self) -> str:
        return self._level

    def set_limit(self, level: str, *, actor: str, reason: str) -> ActionLimitTransition:
        requested = self._validate(level)
        transition = ActionLimitTransition(self._level, requested, str(actor)[:160], str(reason)[:500])
        self._level = requested
        self._history.append(transition)
        return transition

    def allows(self, action_level: str) -> tuple[bool, str]:
        value = self._validate(action_level)
        allowed = self.ORDER.index(value) <= self.ORDER.index(self._level)
        return (
            (True, "action is within the live operator limit")
            if allowed
            else (False, f"action exceeds live operator limit {self._level}")
        )

    def history(self) -> list[dict[str, str]]:
        return [dict(item.__dict__) for item in self._history]


@dataclass(frozen=True)
class PlanEdge:
    prerequisite: str
    dependent: str
    relation: str = "requires"


class PlanGraph:
    def __init__(self):
        self.nodes: dict[str, CandidateAction] = {}
        self.edges: list[PlanEdge] = []

    def add(self, action: CandidateAction, *, prerequisites: Iterable[str] = ()) -> None:
        self.nodes[action.action_id] = action
        for prerequisite in prerequisites:
            edge = PlanEdge(str(prerequisite), action.action_id)
            if edge not in self.edges:
                self.edges.append(edge)

    def ready(self, completed: set[str]) -> list[CandidateAction]:
        blocked = {edge.dependent for edge in self.edges if edge.prerequisite not in completed}
        return [item for key, item in self.nodes.items() if key not in blocked and key not in completed and not item.must_not_try]

    def validate(self) -> list[str]:
        """Return missing prerequisites and dependency cycles before scheduling."""
        errors = [
            f"missing prerequisite: {edge.prerequisite}"
            for edge in self.edges
            if edge.prerequisite not in self.nodes
        ]
        visiting: set[str] = set()
        visited: set[str] = set()
        adjacency: dict[str, list[str]] = {}
        for edge in self.edges:
            adjacency.setdefault(edge.prerequisite, []).append(edge.dependent)

        def visit(node: str) -> None:
            if node in visiting:
                errors.append(f"dependency cycle at: {node}")
                return
            if node in visited:
                return
            visiting.add(node)
            for dependent in adjacency.get(node, []):
                visit(dependent)
            visiting.remove(node)
            visited.add(node)

        for node in self.nodes:
            visit(node)
        return list(dict.fromkeys(errors))

    def parallel_ready(
        self,
        completed: set[str],
        *,
        running_resources: set[str] | None = None,
        max_parallel: int = 4,
    ) -> list[CandidateAction]:
        """Select a safe batch while respecting exclusive resources."""
        resources = set(running_resources or ())
        selected: list[CandidateAction] = []
        for candidate in self.rank_ready(completed):
            candidate_resources = set(candidate.exclusive_resources)
            if not candidate.parallel_safe and selected:
                continue
            if candidate_resources & resources:
                continue
            if any(candidate_resources & set(item.exclusive_resources) for item in selected):
                continue
            selected.append(candidate)
            resources.update(candidate_resources)
            if len(selected) >= max(1, int(max_parallel)):
                break
        return selected

    def rank_ready(self, completed: set[str]) -> list[CandidateAction]:
        return sorted(self.ready(completed), key=lambda item: (-item.score, item.action_id))

    def schedule(self, completed: set[str], *, max_parallel: int = 4) -> list[list[CandidateAction]]:
        """Build deterministic batches until no further node is runnable."""
        batches: list[list[CandidateAction]] = []
        done = set(completed)
        while True:
            batch = self.parallel_ready(done, max_parallel=max_parallel)
            if not batch:
                break
            batches.append(batch)
            done.update(item.action_id for item in batch)
        return batches

    def as_dict(self) -> dict[str, Any]:
        return {"nodes": [item.as_dict() for item in self.nodes.values()], "edges": [edge.__dict__ for edge in self.edges]}


class StagnationDetector:
    def __init__(self, *, max_same_action: int = 2, max_no_gain: int = 3, max_rounds: int = 12):
        self.max_same_action = max(1, max_same_action)
        self.max_no_gain = max(1, max_no_gain)
        self.max_rounds = max(1, max_rounds)
        self._history: list[tuple[str, str]] = []
        self._gains: list[int] = []

    def record(self, *, action_key: str, result_key: str, new_nodes: int = 0) -> None:
        self._history.append((str(action_key), str(result_key)))
        self._gains.append(max(0, int(new_nodes)))
        self._history = self._history[-100:]
        self._gains = self._gains[-100:]

    def diagnose(self) -> dict[str, Any]:
        repeated = 0
        if self._history:
            last = self._history[-1][0]
            for action, _ in reversed(self._history):
                if action != last:
                    break
                repeated += 1
        no_gain = 0
        for gain in reversed(self._gains):
            if gain:
                break
            no_gain += 1
        stalled = repeated > self.max_same_action or no_gain >= self.max_no_gain or len(self._history) >= self.max_rounds and no_gain > 0
        return {"stagnated": stalled, "repeated_action_count": repeated, "no_gain_rounds": no_gain, "recommendation": "change precondition/tool/path or stop" if stalled else "continue"}
