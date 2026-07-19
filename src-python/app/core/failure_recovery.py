"""Deterministic failure taxonomy and recovery ordering."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any


class FailureType(str, Enum):
    TOOL = "tool"
    NETWORK = "network"
    PERMISSION = "permission"
    PRECONDITION = "precondition"
    VERSION_MISMATCH = "version_mismatch"
    TARGET_NEGATIVE = "target_negative"
    POLICY = "policy"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FailureClassification:
    failure_type: FailureType
    confidence: float
    reason: str
    evidence_refs: tuple[str, ...] = ()
    retry_when: tuple[str, ...] = ()
    do_not_repeat: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "failure_type": self.failure_type.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
            "retry_when": list(self.retry_when),
            "do_not_repeat": list(self.do_not_repeat),
        }


class FailureClassifier:
    def classify(self, result: dict[str, Any]) -> FailureClassification:
        text = " ".join(str(result.get(key, "")) for key in ("error", "stderr", "stdout", "reason")).lower()
        evidence_values: list[str] = []
        for key in ("evidence_refs", "evidence_ids", "event_refs"):
            value = result.get(key, ())
            if isinstance(value, (list, tuple, set)):
                evidence_values.extend(str(item) for item in value if str(item).strip())
            elif value:
                evidence_values.append(str(value))
        for key in ("evidence_id", "event_id", "action_id"):
            if result.get(key):
                evidence_values.append(str(result[key]))
        refs = tuple(dict.fromkeys(evidence_values))[:32]

        def failure(
            failure_type: FailureType,
            confidence: float,
            reason: str,
            *,
            retry_when: tuple[str, ...] = (),
            do_not_repeat: tuple[str, ...] = (),
        ) -> FailureClassification:
            return FailureClassification(
                failure_type,
                confidence,
                reason,
                evidence_refs=refs,
                retry_when=retry_when,
                do_not_repeat=do_not_repeat,
            )

        if result.get("policy_blocked") or "outside scope" in text or "policy" in text:
            return failure(FailureType.POLICY, 0.99, "policy decision blocked the action", do_not_repeat=("same action under unchanged scope",))
        if result.get("timed_out") or "timeout" in text or "timed out" in text:
            return failure(FailureType.TIMEOUT, 0.96, "execution exceeded its time budget", retry_when=("timeout or network profile changes",), do_not_repeat=("same timeout and parameters",))
        if any(word in text for word in ("command not found", "no such file", "missing dependency", "unavailable tool")):
            return failure(FailureType.TOOL, 0.95, "tool or dependency is unavailable", retry_when=("tool health becomes ready",), do_not_repeat=("same missing tool",))
        if any(word in text for word in ("connection refused", "network unreachable", "dns", "reset by peer", "temporary failure")):
            return failure(FailureType.NETWORK, 0.9, "network transport failed", retry_when=("fresh reachability observation exists",))
        if any(word in text for word in ("permission denied", "access denied", "operation not permitted", "forbidden")):
            return failure(FailureType.PERMISSION, 0.9, "current identity lacks permission", retry_when=("identity or role changes",))
        if any(word in text for word in ("version mismatch", "not vulnerable version", "unsupported version", "wrong platform")):
            return failure(FailureType.VERSION_MISMATCH, 0.94, "candidate does not match product/platform version", do_not_repeat=("same candidate against same fingerprint",))
        if any(word in text for word in ("precondition", "authentication required", "missing session", "requires ")):
            return failure(FailureType.PRECONDITION, 0.86, "required precondition is absent", retry_when=("precondition becomes true",))
        if result.get("negative_evidence") or any(word in text for word in ("not found", "closed", "not affected", "negative control")):
            return failure(FailureType.TARGET_NEGATIVE, 0.8, "target observation is negative", do_not_repeat=("same probe without new evidence",))
        return failure(FailureType.UNKNOWN, 0.3, "failure signal does not match a deterministic category", retry_when=("new diagnostic evidence exists",))


class RecoveryPlanner:
    ORDER = ("repair_environment", "equivalent_tool", "change_precondition", "new_candidate", "stop")

    def propose(self, classification: FailureClassification, *, equivalent_tools: list[str] | None = None) -> list[dict[str, Any]]:
        plans: list[dict[str, Any]] = []
        if classification.failure_type in {FailureType.TOOL, FailureType.NETWORK, FailureType.TIMEOUT}:
            plans.append({"strategy": "repair_environment", "reason": classification.reason, "evidence_refs": list(classification.evidence_refs)})
        for tool in equivalent_tools or []:
            plans.append({"strategy": "equivalent_tool", "tool": tool, "semantic_difference_required": True, "evidence_refs": list(classification.evidence_refs)})
        if classification.failure_type in {FailureType.PRECONDITION, FailureType.PERMISSION}:
            plans.append({"strategy": "change_precondition", "retry_when": list(classification.retry_when), "evidence_refs": list(classification.evidence_refs)})
        if classification.failure_type not in {FailureType.POLICY, FailureType.TARGET_NEGATIVE, FailureType.VERSION_MISMATCH}:
            plans.append({"strategy": "new_candidate", "source_required": True, "evidence_refs": list(classification.evidence_refs)})
        plans.append({
            "strategy": "stop",
            "do_not_repeat": list(classification.do_not_repeat),
            "evidence_refs": list(classification.evidence_refs),
        })
        order = {name: index for index, name in enumerate(self.ORDER)}
        return sorted(plans, key=lambda item: order[item["strategy"]])


class FailureRecoveryEngine:
    """Classify failures and cap unchanged retries using a stable action key."""

    def __init__(self, *, max_same_action: int = 2) -> None:
        self.max_same_action = max(1, int(max_same_action))
        self._attempts: dict[str, int] = {}

    @staticmethod
    def action_key(result: dict[str, Any]) -> str:
        payload = "|".join(
            str(result.get(key, ""))
            for key in ("action_id", "tool", "target", "port", "args", "command_hash")
        )
        return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()[:24]

    def decide(self, result: dict[str, Any], *, equivalent_tools: list[str] | None = None) -> dict[str, Any]:
        classification = FailureClassifier().classify(result)
        key = self.action_key(result)
        count = self._attempts.get(key, 0) + 1
        self._attempts[key] = count
        if count > self.max_same_action:
            plans = [{
                "strategy": "stop",
                "reason": "unchanged action retry cap reached",
                "do_not_repeat": ["same normalized action without new evidence"],
                "evidence_refs": list(classification.evidence_refs),
            }]
        else:
            plans = RecoveryPlanner().propose(classification, equivalent_tools=equivalent_tools)
        return {
            "action_key": key,
            "attempt_count": count,
            "classification": classification.as_dict(),
            "plans": plans,
            "stopped": plans[0].get("strategy") == "stop" and count > self.max_same_action,
        }


