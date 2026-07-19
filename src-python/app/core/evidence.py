from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .contracts import EvidenceRecord, EvidenceStatus, FindingRecord

_TRANSITIONS: dict[EvidenceStatus, set[EvidenceStatus]] = {
    EvidenceStatus.NOT_STARTED: {
        EvidenceStatus.OUT_OF_SCOPE, EvidenceStatus.BLOCKED_BY_POLICY,
        EvidenceStatus.UNREACHABLE, EvidenceStatus.DISCOVERED,
        EvidenceStatus.CANCELLED,
    },
    EvidenceStatus.OUT_OF_SCOPE: set(),
    EvidenceStatus.BLOCKED_BY_POLICY: set(),
    EvidenceStatus.UNREACHABLE: {EvidenceStatus.DISCOVERED, EvidenceStatus.INCONCLUSIVE, EvidenceStatus.EXHAUSTED},
    EvidenceStatus.UNOBSERVED: {EvidenceStatus.DISCOVERED},
    EvidenceStatus.DISCOVERED: {
        EvidenceStatus.ENUMERATED, EvidenceStatus.SUSPECTED, EvidenceStatus.CANDIDATE,
        EvidenceStatus.POTENTIALLY_VULNERABLE, EvidenceStatus.NOT_APPLICABLE,
        EvidenceStatus.INCONCLUSIVE, EvidenceStatus.FAILED,
    },
    EvidenceStatus.ENUMERATED: {
        EvidenceStatus.SUSPECTED, EvidenceStatus.CANDIDATE,
        EvidenceStatus.POTENTIALLY_VULNERABLE, EvidenceStatus.ATTEMPTED,
        EvidenceStatus.NOT_APPLICABLE, EvidenceStatus.INCONCLUSIVE,
    },
    EvidenceStatus.SUSPECTED: {
        EvidenceStatus.CANDIDATE, EvidenceStatus.POTENTIALLY_VULNERABLE,
        EvidenceStatus.ATTEMPTED, EvidenceStatus.NOT_APPLICABLE, EvidenceStatus.INCONCLUSIVE,
    },
    EvidenceStatus.CANDIDATE: {
        EvidenceStatus.ATTEMPTED, EvidenceStatus.POTENTIALLY_VULNERABLE,
        EvidenceStatus.NOT_APPLICABLE, EvidenceStatus.INCONCLUSIVE,
    },
    EvidenceStatus.POTENTIALLY_VULNERABLE: {
        EvidenceStatus.ATTEMPTED, EvidenceStatus.VULNERABILITY_CONFIRMED,
        EvidenceStatus.NOT_APPLICABLE, EvidenceStatus.INCONCLUSIVE,
    },
    EvidenceStatus.ATTEMPTED: {
        EvidenceStatus.VULNERABILITY_CONFIRMED, EvidenceStatus.VERIFIED_VULNERABLE,
        EvidenceStatus.EXPLOIT_TRIGGERED, EvidenceStatus.EXPLOITED,
        EvidenceStatus.EXHAUSTED,
        EvidenceStatus.NOT_APPLICABLE, EvidenceStatus.FAILED, EvidenceStatus.INCONCLUSIVE,
    },
    EvidenceStatus.VULNERABILITY_CONFIRMED: {
        EvidenceStatus.EXPLOIT_TRIGGERED, EvidenceStatus.SESSION_ESTABLISHED,
        EvidenceStatus.EVIDENCE_COMPLETE, EvidenceStatus.OBJECTIVE_COMPLETED,
    },
    EvidenceStatus.VERIFIED_VULNERABLE: {
        EvidenceStatus.EXPLOITED, EvidenceStatus.EXPLOIT_TRIGGERED,
        EvidenceStatus.SESSION_ESTABLISHED, EvidenceStatus.EVIDENCE_COMPLETE,
    },
    EvidenceStatus.EXPLOIT_TRIGGERED: {
        EvidenceStatus.SESSION_ESTABLISHED, EvidenceStatus.IDENTITY_CONFIRMED,
        EvidenceStatus.EVIDENCE_COMPLETE, EvidenceStatus.OBJECTIVE_COMPLETED,
    },
    EvidenceStatus.EXPLOITED: {
        EvidenceStatus.SESSION_ESTABLISHED, EvidenceStatus.IDENTITY_CONFIRMED,
        EvidenceStatus.EVIDENCE_COMPLETE,
    },
    EvidenceStatus.SESSION_ESTABLISHED: {
        EvidenceStatus.IDENTITY_CONFIRMED, EvidenceStatus.PRIVILEGE_CONFIRMED,
        EvidenceStatus.EVIDENCE_COMPLETE, EvidenceStatus.OBJECTIVE_COMPLETED,
    },
    EvidenceStatus.IDENTITY_CONFIRMED: {
        EvidenceStatus.PRIVILEGE_CONFIRMED, EvidenceStatus.OBJECTIVE_COMPLETED,
        EvidenceStatus.EVIDENCE_COMPLETE,
    },
    EvidenceStatus.PRIVILEGE_CONFIRMED: {EvidenceStatus.OBJECTIVE_COMPLETED, EvidenceStatus.EVIDENCE_COMPLETE},
    EvidenceStatus.OBJECTIVE_COMPLETED: {EvidenceStatus.EVIDENCE_COMPLETE},
    EvidenceStatus.EVIDENCE_COMPLETE: set(),
    EvidenceStatus.EXHAUSTED: {EvidenceStatus.CANDIDATE},
    EvidenceStatus.NOT_APPLICABLE: set(),
    EvidenceStatus.FAILED: {EvidenceStatus.CANDIDATE, EvidenceStatus.ATTEMPTED, EvidenceStatus.CANCELLED},
    EvidenceStatus.INCONCLUSIVE: {EvidenceStatus.CANDIDATE, EvidenceStatus.ATTEMPTED, EvidenceStatus.EXHAUSTED},
    EvidenceStatus.CANCELLED: set(),
}


@dataclass(frozen=True)
class EvidenceDecision:
    accepted: bool
    status: EvidenceStatus
    rule_id: str
    reason: str
    evidence_id: str | None = None


class EvidenceRuleRegistry:
    def __init__(self):
        self._rules: dict[str, Callable[..., EvidenceDecision]] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(self, rule_id: str, rule: Callable[..., EvidenceDecision], *, metadata: dict[str, Any] | None = None) -> None:
        key = str(rule_id).strip()
        if not key or key in self._rules:
            raise ValueError(f"duplicate or empty evidence rule: {rule_id}")
        self._rules[key] = rule
        self._metadata[key] = dict(metadata or {})

    def evaluate(self, rule_id: str, **kwargs) -> EvidenceDecision:
        rule = self._rules.get(rule_id)
        if rule is None:
            return EvidenceDecision(False, EvidenceStatus.ATTEMPTED, rule_id, "unknown evidence rule")
        return rule(**kwargs)

    def metadata(self, rule_id: str) -> dict[str, Any]:
        return dict(self._metadata.get(str(rule_id), {}))

    def manifest(self) -> dict[str, dict[str, Any]]:
        return {key: dict(value) for key, value in self._metadata.items()}


def raw_hash(raw: str | bytes) -> str:
    value = raw if isinstance(raw, bytes) else str(raw).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


class EvidenceStateMachine:
    def transition(self, finding: FindingRecord, target_status: EvidenceStatus, *, evidence: EvidenceRecord | None = None) -> FindingRecord:
        current = EvidenceStatus(finding.status)
        target = EvidenceStatus(target_status)
        if target == current:
            return finding
        if target not in _TRANSITIONS.get(current, set()):
            raise ValueError(f"invalid evidence transition: {current.value} -> {target.value}")
        evidence_required = {
            EvidenceStatus.VERIFIED_VULNERABLE,
            EvidenceStatus.VULNERABILITY_CONFIRMED,
            EvidenceStatus.EXPLOIT_TRIGGERED,
            EvidenceStatus.EXPLOITED,
            EvidenceStatus.SESSION_ESTABLISHED,
            EvidenceStatus.IDENTITY_CONFIRMED,
            EvidenceStatus.PRIVILEGE_CONFIRMED,
            EvidenceStatus.OBJECTIVE_COMPLETED,
            EvidenceStatus.EVIDENCE_COMPLETE,
            EvidenceStatus.EXHAUSTED,
        }
        if target in evidence_required and evidence is None:
            raise ValueError("evidence is required for this state transition")
        if evidence is not None and evidence.task_id != finding.task_id:
            raise ValueError("evidence task does not match finding task")
        evidence_ids = list(finding.evidence_ids)
        if evidence is not None and evidence.evidence_id not in evidence_ids:
            evidence_ids.append(evidence.evidence_id)
        return finding.model_copy(update={"status": target, "evidence_ids": evidence_ids})


def judge_session_evidence(*, target: str, observed_target: str, challenge: str, output: str, identity: str = "") -> EvidenceDecision:
    """Deterministic session proof; output text alone never establishes a session."""
    if target.strip().lower() != observed_target.strip().lower():
        return EvidenceDecision(False, EvidenceStatus.ATTEMPTED, "session.binding.v1", "target binding mismatch")
    if not challenge or challenge not in output:
        return EvidenceDecision(False, EvidenceStatus.ATTEMPTED, "session.challenge.v1", "random challenge was not echoed")
    if not identity.strip():
        return EvidenceDecision(False, EvidenceStatus.ATTEMPTED, "session.identity.v1", "identity proof is missing")
    return EvidenceDecision(True, EvidenceStatus.SESSION_ESTABLISHED, "session.binding.v1", "target, challenge and identity verified")


def judge_privilege_evidence(*, session_verified: bool, identity_output: str, expected_identity: str | None = None) -> EvidenceDecision:
    if not session_verified:
        return EvidenceDecision(False, EvidenceStatus.ATTEMPTED, "privilege.identity.v1", "session is not verified")
    identity = identity_output.strip()
    if not identity:
        return EvidenceDecision(False, EvidenceStatus.ATTEMPTED, "privilege.identity.v1", "identity output is empty")
    if expected_identity and expected_identity not in identity:
        return EvidenceDecision(False, EvidenceStatus.ATTEMPTED, "privilege.identity.v1", "identity does not match expected proof")
    return EvidenceDecision(True, EvidenceStatus.PRIVILEGE_CONFIRMED, "privilege.identity.v1", "identity proof verified")


def judge_interactive_session_evidence(**observation: Any) -> EvidenceDecision:
    """Strict session proof used by the control plane.

    The legacy helper above remains intentionally permissive for old snapshots;
    new execution paths should use this rule, which requires two distinct
    command outputs and a live heartbeat in addition to binding and identity.
    """
    from .judges import InteractiveSessionJudge

    result = InteractiveSessionJudge().evaluate(observation)
    return EvidenceDecision(
        result.accepted,
        result.status,
        result.judge_id,
        result.reason,
    )


def canonical_status_manifest() -> dict[str, list[str]]:
    """Return the transition graph as JSON-ready data for UI and reports."""
    return {
        status.value: sorted(next_status.value for next_status in transitions)
        for status, transitions in _TRANSITIONS.items()
    }
