"""Bridge legacy tool results into the canonical evidence/event vocabulary."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Literal

from .contracts import EvidenceRecord, EvidenceStatus, FindingRecord, PolicyDecisionKind
from .judges import JudgeRegistry, JudgeResult

_REPORTABLE_STATUSES = frozenset(
    {
        EvidenceStatus.VULNERABILITY_CONFIRMED,
        EvidenceStatus.VERIFIED_VULNERABLE,
        EvidenceStatus.EXPLOIT_TRIGGERED,
        EvidenceStatus.EXPLOITED,
        EvidenceStatus.SESSION_ESTABLISHED,
        EvidenceStatus.IDENTITY_CONFIRMED,
        EvidenceStatus.PRIVILEGE_CONFIRMED,
        EvidenceStatus.OBJECTIVE_COMPLETED,
    }
)


@dataclass(frozen=True)
class BridgeResult:
    evidence: EvidenceRecord
    judge: JudgeResult
    finding: FindingRecord | None = None


def _digest(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8", errors="replace")).hexdigest()


def _redact(value: str, limit: int = 1000) -> str:
    text = str(value or "")
    text = re.sub(r"(?i)(password|passwd|token|api[_-]?key|secret)(\s*[=:]\s*)\S+", r"\1\2[REDACTED]", text)
    text = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)\S+", r"\1[REDACTED]", text)
    return text[:limit]


class EvidenceBridge:
    """Create and persist one typed evidence record per completed action.

    The bridge deliberately treats unstructured output as an observation only;
    high-confidence states come from a registered deterministic judge.
    """

    def __init__(self, registry: JudgeRegistry | None = None) -> None:
        self.registry = registry or JudgeRegistry()

    def ingest(
        self,
        *,
        task_id: str,
        target: str,
        action_id: str,
        tool: str,
        action_type: str = "",
        result: dict[str, Any] | None = None,
        raw_output: str = "",
        mission_id: str = "mission-local",
        scope_decision: PolicyDecisionKind | str | None = None,
    ) -> BridgeResult:
        payload = dict(result or {})
        raw = str(raw_output or payload.get("full_output") or payload.get("stdout") or "")
        observation = self._observation(payload, raw, target=target)
        forced_status = self._forced_status(payload)
        judge_id = self._select_judge(payload, observation, tool=tool, action_type=action_type)
        if forced_status is not None:
            judge = JudgeResult(
                accepted=False,
                status=forced_status,
                judge_id=f"bridge.{forced_status.value.lower()}",
                judge_version="1.0.0",
                reason=(
                    "action was blocked by scope policy"
                    if forced_status == EvidenceStatus.BLOCKED_BY_POLICY
                    else "action cancellation was observed"
                    if forced_status == EvidenceStatus.CANCELLED
                    else "action result contains an execution error"
                ),
                confidence=0.95 if forced_status == EvidenceStatus.BLOCKED_BY_POLICY else 0.8,
                negative=True,
            )
        elif judge_id:
            judge = self.registry.evaluate(judge_id, observation)
        else:
            judge = JudgeResult(
                accepted=False,
                status=EvidenceStatus.INCONCLUSIVE,
                judge_id="bridge.inconclusive",
                judge_version="1.0.0",
                reason="structured evidence for a deterministic judge is missing",
                confidence=0.05,
                negative=True,
            )
        raw_hash = _digest(raw)
        evidence_id = f"evidence_{_digest(f'{task_id}:{action_id}:{raw_hash}:{judge.judge_id}')[:24]}"
        normalized = {
            "tool": str(tool)[:120],
            "action_type": str(action_type)[:80],
            "returncode": payload.get("returncode"),
            "facts": [dict(item) for item in judge.facts],
            "result_keys": sorted(str(key) for key in payload)[:80],
        }
        evidence = EvidenceRecord(
            evidence_id=evidence_id,
            task_id=str(task_id)[:128],
            mission_id=str(mission_id or "mission-local")[:128],
            target=str(target)[:255],
            evidence_type=self._evidence_type(judge.status, tool, action_type),
            status=judge.status,
            rule_id=judge.judge_id,
            rule_version=judge.judge_version,
            raw_hash=raw_hash,
            raw_ref=f"action://{str(task_id)[:80]}/{str(action_id)[:80]}",
            normalized=normalized,
            action_id=str(action_id)[:128],
            source="tool",
            source_type="legacy-action-result",
            source_name=str(tool)[:120],
            command_hash=_digest(_redact(str(payload.get("command", "")), 2000)),
            sanitized_command=_redact(str(payload.get("command", "")), 1000),
            confidence=max(0.0, min(1.0, float(judge.confidence))),
            reproducible=judge.reproducible,
            judge_id=judge.judge_id,
            judge_version=judge.judge_version,
            judge_result=judge.as_dict(),
            scope_decision=self._scope_decision(scope_decision),
            negative=bool(judge.negative),
            sensitivity="sensitive" if any(word in str(tool).lower() for word in ("cred", "session", "auth")) else "internal",
            integrity={"raw_sha256": raw_hash, "normalized_sha256": _digest(str(normalized))},
        )
        finding = self._finding_for(evidence, judge, tool=tool)
        return BridgeResult(evidence=evidence, judge=judge, finding=finding)

    @staticmethod
    def _forced_status(payload: dict[str, Any]) -> EvidenceStatus | None:
        if payload.get("policy_blocked") or str(payload.get("status", "")).lower() in {"blocked", "out_of_scope"}:
            return EvidenceStatus.BLOCKED_BY_POLICY
        if payload.get("cancelled") or str(payload.get("status", "")).lower() in {"cancelled", "cancelling"}:
            return EvidenceStatus.CANCELLED
        if payload.get("error") and str(payload.get("failure_type", "")).lower() in {"network_unreachable", "unreachable", "timeout"}:
            return EvidenceStatus.UNREACHABLE
        if payload.get("error"):
            return EvidenceStatus.FAILED
        return None

    def persist(self, state: Any, bridged: BridgeResult) -> None:
        """Persist through the legacy State adapter while emitting typed events."""
        state.record_canonical_evidence(
            bridged.evidence.model_dump(mode="json"),
            finding=bridged.finding.model_dump(mode="json") if bridged.finding else None,
        )

    @staticmethod
    def _scope_decision(value: PolicyDecisionKind | str | None) -> PolicyDecisionKind | None:
        if value is None or value == "":
            return None
        try:
            return PolicyDecisionKind(value)
        except ValueError:
            return None

    @staticmethod
    def _observation(payload: dict[str, Any], raw: str, *, target: str) -> dict[str, Any]:
        observation: dict[str, Any] = dict(payload)
        observation.setdefault("target", target)
        parsed = payload.get("parsed")
        if isinstance(parsed, list) and parsed:
            first = parsed[0]
            if isinstance(first, dict):
                for key, value in first.items():
                    observation.setdefault(str(key), value)
        observation.setdefault("tool_output", raw[:4000])
        proof = payload.get("session_proof")
        if isinstance(proof, dict):
            observation.update(proof)
        return observation

    @staticmethod
    def _select_judge(payload: dict[str, Any], observation: dict[str, Any], *, tool: str, action_type: str) -> str:
        action = f"{action_type} {tool}".lower()
        proof = payload.get("session_proof")
        if isinstance(proof, dict):
            return "interactive-session"
        if any(key in observation for key in ("baseline", "probe", "reproduction")):
            return "vulnerability-behavior"
        if "marker" in observation or "second_command_ok" in observation:
            return "command-execution"
        if "status_code" in observation or "headers" in observation or "body" in observation:
            return "http-response"
        if any(key in observation for key in ("service", "banner", "handshake", "http", "tls")):
            return "service-fingerprint"
        if "port" in observation and any(key in observation for key in ("state", "transport_result")):
            return "port-state"
        if any(word in action for word in ("reach", "connect", "transport")) and "transport_result" in observation:
            return "reachability"
        return ""

    @staticmethod
    def _evidence_type(status: EvidenceStatus, tool: str, action_type: str) -> str:
        if status in _REPORTABLE_STATUSES:
            return "verified-finding"
        if action_type:
            return str(action_type).strip().lower()[:80]
        return f"tool:{str(tool).strip().lower()[:60]}"

    @staticmethod
    def _finding_for(evidence: EvidenceRecord, judge: JudgeResult, *, tool: str) -> FindingRecord | None:
        if judge.status not in _REPORTABLE_STATUSES:
            return None
        finding_id = f"finding_{_digest(evidence.evidence_id)[:24]}"
        severity: Literal["info", "high"] = "high" if judge.status in {
            EvidenceStatus.VULNERABILITY_CONFIRMED,
            EvidenceStatus.VERIFIED_VULNERABLE,
            EvidenceStatus.EXPLOITED,
        } else "info"
        return FindingRecord(
            finding_id=finding_id,
            task_id=evidence.task_id,
            title=f"{str(tool).strip()[:80]}: {judge.reason[:160]}",
            target=evidence.target,
            status=judge.status,
            severity=severity,
            impact=judge.reason[:500],
            evidence_ids=[evidence.evidence_id],
            status_reason=judge.reason[:500],
            judge_id=judge.judge_id,
        )


__all__ = ["BridgeResult", "EvidenceBridge"]
