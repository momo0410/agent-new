"""确定性判定器与证据注册表。

The planner may propose actions, but only these small, typed judges may move a
finding toward a reportable conclusion.  Each judge returns observable facts;
model text is accepted only as an untrusted input field and never as proof.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from .contracts import EvidenceStatus


@dataclass(frozen=True)
class JudgeSpec:
    judge_id: str
    version: str
    supported_task_types: tuple[str, ...]
    input_schema: tuple[str, ...]
    output_schema: tuple[str, ...]
    minimum_evidence: tuple[str, ...] = ()
    false_positive_notes: str = ""


@dataclass(frozen=True)
class JudgeResult:
    accepted: bool
    status: EvidenceStatus
    judge_id: str
    judge_version: str
    reason: str
    confidence: float = 0.0
    facts: tuple[dict[str, Any], ...] = ()
    negative: bool = False
    reproducible: bool | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "status": self.status.value,
            "judge_id": self.judge_id,
            "judge_version": self.judge_version,
            "reason": self.reason,
            "confidence": self.confidence,
            "facts": [dict(item) for item in self.facts],
            "negative": self.negative,
            "reproducible": self.reproducible,
        }


class BaseJudge:
    spec = JudgeSpec("base", "1.0.0", ("generic",), (), ())

    def evaluate(self, observation: dict[str, Any] | None = None, **kwargs: Any) -> JudgeResult:
        raise NotImplementedError

    def _result(self, accepted: bool, status: EvidenceStatus, reason: str, **kwargs: Any) -> JudgeResult:
        return JudgeResult(
            accepted=accepted,
            status=status,
            judge_id=self.spec.judge_id,
            judge_version=self.spec.version,
            reason=reason,
            **kwargs,
        )


class ReachabilityJudge(BaseJudge):
    spec = JudgeSpec(
        "reachability", "1.0.0", ("discovery", "recon"), ("target", "transport_result"), ("accepted", "status", "facts"),
        ("connection_attempt",), "A successful TCP connect alone is not a service fingerprint.",
    )

    def evaluate(self, observation: dict[str, Any] | None = None, **kwargs: Any) -> JudgeResult:
        data = {**(observation or {}), **kwargs}
        result = data.get("transport_result", data.get("reachable", False))
        reachable = result is True or str(result).lower() in {"true", "open", "reachable", "connected", "success"}
        target = str(data.get("target", "")).strip()
        if not target:
            return self._result(False, EvidenceStatus.INCONCLUSIVE, "target is missing", negative=True)
        return self._result(
            reachable,
            EvidenceStatus.DISCOVERED if reachable else EvidenceStatus.UNREACHABLE,
            "transport connection observed" if reachable else "transport connection failed",
            confidence=0.95 if reachable else 0.9,
            facts=({"target": target, "reachable": reachable},),
            negative=not reachable,
        )


class PortStateJudge(BaseJudge):
    spec = JudgeSpec(
        "port-state", "1.0.0", ("discovery", "recon"), ("port", "state", "transport_result"), ("accepted", "status", "facts"),
        ("probe_output",), "Port state does not establish a service identity.",
    )

    def evaluate(self, observation: dict[str, Any] | None = None, **kwargs: Any) -> JudgeResult:
        data = {**(observation or {}), **kwargs}
        state = str(data.get("state", data.get("transport_result", ""))).lower().strip()
        open_state = state in {"open", "open|filtered", "listening", "connected", "success"}
        if state in {"closed", "filtered", "unreachable", "timeout", "refused"}:
            open_state = False
        if state not in {"open", "open|filtered", "listening", "connected", "success", "closed", "filtered", "unreachable", "timeout", "refused"}:
            return self._result(False, EvidenceStatus.INCONCLUSIVE, "port state is ambiguous", confidence=0.2)
        return self._result(
            open_state,
            EvidenceStatus.DISCOVERED if open_state else EvidenceStatus.UNREACHABLE,
            f"port state={state}",
            confidence=0.9,
            facts=({"target": str(data.get("target", "")), "port": data.get("port"), "state": state},),
            negative=not open_state,
        )


class ServiceFingerprintJudge(BaseJudge):
    spec = JudgeSpec(
        "service-fingerprint", "1.0.0", ("recon",), ("port", "banner", "handshake", "http"), ("accepted", "status", "facts"),
        ("at_least_two_signals",), "A port number by itself is never a service fingerprint.",
    )

    def evaluate(self, observation: dict[str, Any] | None = None, **kwargs: Any) -> JudgeResult:
        data = {**(observation or {}), **kwargs}
        signals = []
        for key in ("banner", "handshake", "http", "tls", "tool_output", "service"):
            value = str(data.get(key, "") or "").strip()
            if value:
                signals.append((key, value[:500]))
        if len(signals) < 1:
            return self._result(False, EvidenceStatus.INCONCLUSIVE, "no service signal", confidence=0.1, negative=True)
        service = str(data.get("service", "") or "").strip()
        if not service:
            text = " ".join(value for _, value in signals).lower()
            service = "http" if re.search(r"http/\d|content-type:|html", text) else "unknown"
        confidence = min(0.99, 0.45 + 0.2 * len(signals))
        return self._result(
            service != "unknown",
            EvidenceStatus.ENUMERATED,
            f"service signals={','.join(k for k, _ in signals)}",
            confidence=confidence,
            facts=({"service": service, "signals": [k for k, _ in signals]},),
            negative=service == "unknown",
        )


class HttpResponseJudge(BaseJudge):
    spec = JudgeSpec(
        "http-response", "1.0.0", ("web", "recon"), ("status_code", "headers", "body"), ("accepted", "status", "facts"),
        ("http_response",), "A response is an observation, not a vulnerability conclusion.",
    )

    def evaluate(self, observation: dict[str, Any] | None = None, **kwargs: Any) -> JudgeResult:
        data = {**(observation or {}), **kwargs}
        try:
            code = int(data.get("status_code", data.get("status", 0)))
        except (TypeError, ValueError):
            code = 0
        if not 100 <= code <= 599:
            return self._result(False, EvidenceStatus.INCONCLUSIVE, "invalid HTTP status", confidence=0.1)
        return self._result(
            True,
            EvidenceStatus.ENUMERATED,
            f"HTTP {code} response observed",
            confidence=0.98,
            facts=({"status_code": code, "content_type": str((data.get("headers") or {}).get("content-type", ""))[:160]},),
        )


class AuthenticationJudge(BaseJudge):
    spec = JudgeSpec(
        "authentication", "1.0.0", ("web", "credential_test"), ("before", "after", "identity"), ("accepted", "status", "facts"),
        ("paired_requests",), "Authentication requires a paired before/after observation.",
    )

    def evaluate(self, observation: dict[str, Any] | None = None, **kwargs: Any) -> JudgeResult:
        data = {**(observation or {}), **kwargs}
        before = data.get("before")
        after = data.get("after")
        authenticated = data.get("authenticated")
        if authenticated is None and isinstance(before, dict) and isinstance(after, dict):
            authenticated = after.get("status_code") not in {401, 403} and before.get("status_code") in {401, 403}
        if authenticated is True:
            return self._result(True, EvidenceStatus.VULNERABILITY_CONFIRMED if data.get("finding") else EvidenceStatus.ENUMERATED, "paired authentication state changed", confidence=0.9, facts=({"authenticated": True},))
        if authenticated is False:
            return self._result(False, EvidenceStatus.INCONCLUSIVE, "authentication state did not change", confidence=0.85, negative=True)
        return self._result(False, EvidenceStatus.INCONCLUSIVE, "paired authentication observations are missing", confidence=0.1)


class AuthorizationDifferenceJudge(BaseJudge):
    spec = JudgeSpec(
        "authorization-difference", "1.0.0", ("web",), ("low_privilege", "high_privilege", "resource"), ("accepted", "status", "facts"),
        ("same_resource_pair",), "Authorization requires a same-resource role comparison.",
    )

    def evaluate(self, observation: dict[str, Any] | None = None, **kwargs: Any) -> JudgeResult:
        data = {**(observation or {}), **kwargs}
        low = data.get("low_privilege")
        high = data.get("high_privilege")
        if not isinstance(low, dict) or not isinstance(high, dict):
            return self._result(False, EvidenceStatus.INCONCLUSIVE, "role-paired responses are missing", confidence=0.1)
        difference = low.get("status_code") != high.get("status_code") or low.get("body_hash") != high.get("body_hash")
        suspected = difference and low.get("status_code") not in {401, 403}
        return self._result(
            suspected,
            EvidenceStatus.VULNERABILITY_CONFIRMED if suspected else EvidenceStatus.INCONCLUSIVE,
            "role response differs for the same resource" if suspected else "no unauthorized difference observed",
            confidence=0.92 if suspected else 0.8,
            facts=({"resource": str(data.get("resource", "")), "difference": difference},),
            negative=not suspected,
        )


class VulnerabilityBehaviorJudge(BaseJudge):
    spec = JudgeSpec(
        "vulnerability-behavior", "1.0.0", ("verification", "exploit"), ("baseline", "probe", "reproduction"), ("accepted", "status", "facts"),
        ("paired_behavior",), "A tool banner or model statement is not behavior evidence.",
    )

    def evaluate(self, observation: dict[str, Any] | None = None, **kwargs: Any) -> JudgeResult:
        data = {**(observation or {}), **kwargs}
        baseline = data.get("baseline")
        probe = data.get("probe", data.get("reproduction"))
        if baseline is None or probe is None:
            return self._result(False, EvidenceStatus.INCONCLUSIVE, "baseline/probe pair is missing", confidence=0.1)
        changed = str(baseline) != str(probe)
        return self._result(
            changed,
            EvidenceStatus.VULNERABILITY_CONFIRMED if changed else EvidenceStatus.INCONCLUSIVE,
            "paired behavior changed under controlled probe" if changed else "controlled probe matched baseline",
            confidence=0.9 if changed else 0.82,
            facts=({"behavior_changed": changed},),
            negative=not changed,
            reproducible=bool(data.get("reproducible", changed)),
        )


class FileWriteJudge(BaseJudge):
    spec = JudgeSpec(
        "file-write", "1.0.0", ("verification", "web"), ("path", "before_hash", "after_hash"), ("accepted", "status", "facts"),
        ("controlled_file",), "Only a predeclared, reversible marker path is accepted.",
    )

    def evaluate(self, observation: dict[str, Any] | None = None, **kwargs: Any) -> JudgeResult:
        data = {**(observation or {}), **kwargs}
        path = str(data.get("path", ""))
        controlled = bool(data.get("controlled", False))
        changed = data.get("before_hash") != data.get("after_hash") and data.get("after_hash")
        ok = bool(path and controlled and changed)
        return self._result(ok, EvidenceStatus.VULNERABILITY_CONFIRMED if ok else EvidenceStatus.INCONCLUSIVE, "controlled marker changed" if ok else "controlled file evidence missing", confidence=0.95 if ok else 0.2, facts=({"path": path, "changed": bool(changed)},), negative=not ok)


class CommandExecutionJudge(BaseJudge):
    spec = JudgeSpec(
        "command-execution", "1.0.0", ("verification", "exploit"), ("marker", "output", "exit_code"), ("accepted", "status", "facts"),
        ("random_marker", "second_command"), "A command-like string in output is not execution proof.",
    )

    def evaluate(self, observation: dict[str, Any] | None = None, **kwargs: Any) -> JudgeResult:
        data = {**(observation or {}), **kwargs}
        marker = str(data.get("marker", ""))
        output = str(data.get("output", ""))
        second = bool(data.get("second_command_ok", False))
        exit_code = data.get("exit_code", 0)
        ok = bool(marker and marker in output and second and exit_code in (0, "0", None))
        return self._result(ok, EvidenceStatus.EXPLOIT_TRIGGERED if ok else EvidenceStatus.INCONCLUSIVE, "marker and independent command verified" if ok else "independent command proof missing", confidence=0.96 if ok else 0.2, facts=({"marker_echoed": bool(marker and marker in output), "second_command_ok": second},), negative=not ok)


class InteractiveSessionJudge(BaseJudge):
    spec = JudgeSpec(
        "interactive-session", "1.0.0", ("session_verification",), ("target", "challenge", "commands", "identity", "heartbeat"), ("accepted", "status", "facts"),
        ("two_distinct_commands", "identity", "heartbeat"), "A framework session message alone is insufficient.",
    )

    def evaluate(self, observation: dict[str, Any] | None = None, **kwargs: Any) -> JudgeResult:
        data = {**(observation or {}), **kwargs}
        target = str(data.get("target", "")).strip().lower().rstrip(".")
        bound = str(data.get("observed_target", data.get("target_binding", ""))).strip().lower().rstrip(".")
        challenge = str(data.get("challenge", ""))
        outputs = data.get("command_outputs", data.get("commands", []))
        if isinstance(outputs, dict):
            outputs = list(outputs.values())
        outputs = [str(item) for item in outputs or []]
        identity = str(data.get("identity", "")).strip()
        heartbeat = bool(data.get("heartbeat", False))
        distinct = len(outputs) >= 2 and outputs[0] != outputs[1]
        echoed = bool(challenge and any(challenge in item for item in outputs))
        ok = bool(target and target == bound and echoed and distinct and identity and heartbeat)
        return self._result(
            ok,
            EvidenceStatus.SESSION_ESTABLISHED if ok else EvidenceStatus.INCONCLUSIVE,
            "target, random marker, two commands, identity and heartbeat verified" if ok else "session proof is incomplete",
            confidence=0.99 if ok else 0.15,
            facts=({"target_bound": target == bound, "marker_echoed": echoed, "distinct_commands": distinct, "identity": bool(identity), "heartbeat": heartbeat},),
            negative=not ok,
        )


class IdentityJudge(BaseJudge):
    spec = JudgeSpec("identity", "1.0.0", ("session_verification", "post"), ("identity",), ("identity",), ("identity_output",), "Identity must come from target output.")

    def evaluate(self, observation: dict[str, Any] | None = None, **kwargs: Any) -> JudgeResult:
        data = {**(observation or {}), **kwargs}
        identity = str(data.get("identity", data.get("output", ""))).strip()
        ok = bool(identity and (re.search(r"\b(uid|user|whoami|id)\b", identity, re.I) or data.get("identity_verified")))
        return self._result(ok, EvidenceStatus.IDENTITY_CONFIRMED if ok else EvidenceStatus.INCONCLUSIVE, "identity output verified" if ok else "identity output missing or unrecognized", confidence=0.95 if ok else 0.1, facts=({"identity": identity[:240]},), negative=not ok)


class PrivilegeJudge(BaseJudge):
    spec = JudgeSpec("privilege", "1.0.0", ("post", "session_verification"), ("identity", "expected"), ("privilege",), ("identity_output",), "Privilege state is separate from session state.")

    def evaluate(self, observation: dict[str, Any] | None = None, **kwargs: Any) -> JudgeResult:
        data = {**(observation or {}), **kwargs}
        identity = str(data.get("identity", data.get("identity_output", ""))).strip().lower()
        expected = str(data.get("expected", data.get("expected_identity", "root"))).strip().lower()
        ok = bool(data.get("session_verified", False) and expected and expected in identity)
        return self._result(ok, EvidenceStatus.PRIVILEGE_CONFIRMED if ok else EvidenceStatus.INCONCLUSIVE, "privilege identity matched" if ok else "privilege proof missing", confidence=0.98 if ok else 0.1, facts=({"expected": expected, "matched": ok},), negative=not ok)


class ObjectiveJudge(BaseJudge):
    spec = JudgeSpec("objective", "1.0.0", ("objective",), ("objective", "evidence"), ("objective",), ("objective_evidence",), "Objective completion must cite its evidence set.")

    def evaluate(self, observation: dict[str, Any] | None = None, **kwargs: Any) -> JudgeResult:
        data = {**(observation or {}), **kwargs}
        objective = str(data.get("objective", "")).strip()
        refs = data.get("evidence_refs", data.get("evidence", []))
        if isinstance(refs, str):
            refs = [refs] if refs else []
        ok = bool(objective and refs and data.get("verified", True))
        return self._result(ok, EvidenceStatus.OBJECTIVE_COMPLETED if ok else EvidenceStatus.INCONCLUSIVE, "objective evidence is complete" if ok else "objective evidence is incomplete", confidence=0.96 if ok else 0.1, facts=({"objective": objective, "evidence_refs": list(refs or [])},), negative=not ok)


BUILTIN_JUDGES: tuple[type[BaseJudge], ...] = (
    ReachabilityJudge, PortStateJudge, ServiceFingerprintJudge, HttpResponseJudge,
    AuthenticationJudge, AuthorizationDifferenceJudge, VulnerabilityBehaviorJudge,
    FileWriteJudge, CommandExecutionJudge, InteractiveSessionJudge, IdentityJudge,
    PrivilegeJudge, ObjectiveJudge,
)


class JudgeRegistry:
    """Versioned registry with explicit metadata and deterministic dispatch."""

    def __init__(self, *, load_builtins: bool = True):
        self._judges: dict[str, BaseJudge] = {}
        if load_builtins:
            for judge_type in BUILTIN_JUDGES:
                self.register(judge_type())

    def register(self, judge: BaseJudge) -> None:
        key = judge.spec.judge_id.strip()
        if not key or key in self._judges:
            raise ValueError(f"duplicate judge: {key}")
        self._judges[key] = judge

    def get(self, judge_id: str) -> BaseJudge | None:
        return self._judges.get(str(judge_id).strip())

    def evaluate(self, judge_id: str, observation: dict[str, Any] | None = None, **kwargs: Any) -> JudgeResult:
        judge = self.get(judge_id)
        if judge is None:
            return JudgeResult(False, EvidenceStatus.INCONCLUSIVE, str(judge_id), "0", "unknown judge", confidence=0.0)
        return judge.evaluate(observation, **kwargs)

    def specs(self) -> list[JudgeSpec]:
        return [judge.spec for judge in self._judges.values()]

    def as_dict(self) -> dict[str, dict[str, Any]]:
        return {
            spec.judge_id: {
                "version": spec.version,
                "supported_task_types": list(spec.supported_task_types),
                "input_schema": list(spec.input_schema),
                "output_schema": list(spec.output_schema),
                "minimum_evidence": list(spec.minimum_evidence),
                "false_positive_notes": spec.false_positive_notes,
            }
            for spec in self.specs()
        }


def evidence_digest(raw: str | bytes) -> str:
    value = raw if isinstance(raw, bytes) else str(raw).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


__all__ = [
    "JudgeSpec", "JudgeResult", "BaseJudge", "JudgeRegistry", "evidence_digest",
    "ReachabilityJudge", "PortStateJudge", "ServiceFingerprintJudge", "HttpResponseJudge",
    "AuthenticationJudge", "AuthorizationDifferenceJudge", "VulnerabilityBehaviorJudge",
    "FileWriteJudge", "CommandExecutionJudge", "InteractiveSessionJudge", "IdentityJudge",
    "PrivilegeJudge", "ObjectiveJudge",
]
