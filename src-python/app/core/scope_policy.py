from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import secrets
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from .contracts import ActionEnvelope, ActionLevel, PolicyDecisionKind, ScopeContract
from .policy_templates import CoursePolicyError, CoursePolicyRegistry


class ScopeTokenError(ValueError):
    pass


class PolicyDecision(dict):
    """JSON-compatible decision object kept intentionally small for audit logs."""

    @property
    def allowed(self) -> bool:
        return bool(self.get("allowed")) and self.get("decision", PolicyDecisionKind.ALLOW.value) != PolicyDecisionKind.DENY.value

    @property
    def decision(self) -> str:
        return str(self.get("decision", PolicyDecisionKind.ALLOW.value))


class ScopePolicy:
    def __init__(
        self,
        secret: bytes | None = None,
        *,
        token_ttl_seconds: int = 900,
        course_policies: CoursePolicyRegistry | None = None,
    ):
        self._secret = secret or secrets.token_bytes(32)
        self.token_ttl_seconds = max(60, min(token_ttl_seconds, 86400))
        self._lock = threading.RLock()
        self._commands: dict[str, int] = {}
        self._requests: dict[str, int] = {}
        self._bruteforce: dict[str, int] = {}
        self._active: dict[str, int] = {}
        self._request_times: dict[str, list[float]] = {}
        self._decision_cache: dict[str, PolicyDecision] = {}
        self._emergency_stop = False
        self._audit: list[dict[str, Any]] = []
        self._course_policies = course_policies

    def bind_course_policies(self, registry: CoursePolicyRegistry | None) -> None:
        """Attach the administrator-owned course policy registry."""
        with self._lock:
            self._course_policies = registry

    @staticmethod
    def _contract_hash(contract: ScopeContract) -> str:
        return contract.canonical_hash()

    def issue_token(self, contract: ScopeContract, *, now: datetime | None = None) -> str:
        current = now or datetime.now(timezone.utc)
        if contract.expires_at <= current:
            raise ScopeTokenError("scope contract expired")
        template_hash = ""
        if self._course_policies is not None and contract.policy_template_id:
            try:
                template = self._course_policies.enforce(contract)
                template_hash = template.canonical_hash()
            except CoursePolicyError as exc:
                raise ScopeTokenError(str(exc)) from exc
        payload = {
            "token_id": secrets.token_urlsafe(12),
            "scope_id": contract.scope_id,
            "mission_id": contract.mission_id,
            "revision": contract.revision,
            "contract_hash": self._contract_hash(contract),
            "policy_template_hash": template_hash,
            "issued_at": current.isoformat(),
            "expires_at": min(contract.expires_at, current + timedelta(seconds=self.token_ttl_seconds)).isoformat(),
        }
        encoded = self._encode(payload)
        signature = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
        return f"{encoded}.{self._b64(signature)}"

    def verify_token(self, token: str, contract: ScopeContract, *, now: datetime | None = None) -> dict[str, Any]:
        try:
            encoded, signature = str(token).split(".", 1)
            expected = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
            actual = self._unb64(signature)
            if not hmac.compare_digest(expected, actual):
                raise ScopeTokenError("invalid scope token signature")
            payload = json.loads(self._unb64(encoded).decode("utf-8"))
            current = now or datetime.now(timezone.utc)
            expiry = datetime.fromisoformat(payload["expires_at"])
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= current:
                raise ScopeTokenError("scope token expired")
            if (
                payload.get("scope_id") != contract.scope_id
                or payload.get("mission_id") != contract.mission_id
                or payload.get("revision") != contract.revision
                or payload.get("contract_hash") != self._contract_hash(contract)
            ):
                raise ScopeTokenError("scope token does not match contract")
            if self._course_policies is not None and contract.policy_template_id:
                try:
                    template = self._course_policies.enforce(contract)
                except CoursePolicyError as exc:
                    raise ScopeTokenError(str(exc)) from exc
                if payload.get("policy_template_hash") != template.canonical_hash():
                    raise ScopeTokenError("scope token does not match course policy template")
            return payload
        except ScopeTokenError:
            raise
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            raise ScopeTokenError("malformed scope token") from exc

    @staticmethod
    def _b64(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    @staticmethod
    def _unb64(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

    def _encode(self, payload: dict[str, Any]) -> str:
        return self._b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))

    @staticmethod
    def target_in_scope(target: str, contract: ScopeContract) -> bool:
        candidate = str(target or "").strip().lower().rstrip(".")
        if not candidate:
            return False
        if candidate in {value.lower().rstrip(".") for value in contract.allowed_targets}:
            return True
        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError:
            ip = None
        if ip is not None:
            for cidr in contract.allowed_cidrs:
                try:
                    if ip in ipaddress.ip_network(cidr, strict=False):
                        return True
                except ValueError:
                    continue
            return False
        for domain in contract.allowed_domains:
            normalized = domain.lower().rstrip(".")
            if normalized.startswith("*."):
                suffix = normalized[2:]
                if candidate.endswith("." + suffix) and candidate != suffix:
                    return True
            elif candidate == normalized or candidate.endswith("." + normalized):
                return True
        return False

    @classmethod
    def resolved_targets_in_scope(cls, target: str, contract: ScopeContract, *, resolver: Any = None) -> tuple[bool, list[str], str]:
        """Resolve every address and validate every result before a request.

        Explicit IP/fixture targets do not require DNS.  A domain that resolves
        to a mixed in/out-of-scope set is rejected as a whole.
        """
        candidate = str(target or "").strip()
        if not cls.target_in_scope(candidate, contract):
            return False, [], "target is outside scope"
        try:
            ipaddress.ip_address(candidate)
            return True, [candidate], "target authorized"
        except ValueError:
            pass
        if candidate.lower().rstrip(".") in {str(item).lower().rstrip(".") for item in contract.allowed_targets} and resolver is None:
            # An explicitly listed symbolic target is already bounded.  Still
            # resolve when a resolver is supplied so rebinding is observable.
            return True, [candidate], "explicit target authorized"
        resolve = resolver or socket.getaddrinfo
        try:
            infos = resolve(candidate, None, type=socket.SOCK_STREAM)
            addresses = sorted({str(item[4][0]) for item in infos if item and item[4]})
        except (OSError, TypeError, ValueError):
            return False, [], "DNS resolution failed"
        if not addresses or not all(cls.target_in_scope(address, contract) for address in addresses):
            return False, addresses, "resolved target is outside scope"
        return True, addresses, "all resolved targets authorized"

    @staticmethod
    def port_in_scope(port: int | None, contract: ScopeContract) -> bool:
        if port is None:
            return True
        if port in contract.allowed_ports:
            return True
        return any(item.contains(port) for item in contract.allowed_port_ranges)

    def set_emergency_stop(self, enabled: bool = True) -> None:
        with self._lock:
            self._emergency_stop = bool(enabled)

    def emergency_stop_enabled(self) -> bool:
        with self._lock:
            return self._emergency_stop

    def release_action(self, task_id: str) -> None:
        with self._lock:
            self._active[task_id] = max(0, self._active.get(task_id, 0) - 1)

    def usage(self, task_id: str) -> dict[str, int]:
        with self._lock:
            return {
                "commands": self._commands.get(task_id, 0),
                "network_requests": self._requests.get(task_id, 0),
                "bruteforce_attempts": self._bruteforce.get(task_id, 0),
                "active": self._active.get(task_id, 0),
            }

    def audit_events(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._audit]

    def _record_audit(self, envelope: ActionEnvelope, decision: PolicyDecision, *, reason: str) -> None:
        self._audit.append({
            "time": datetime.now(timezone.utc).isoformat(),
            "action_id": envelope.action_id,
            "task_id": envelope.task_id,
            "scope_id": envelope.scope_id,
            "target": envelope.target,
            "port": envelope.port,
            "plugin": envelope.plugin,
            "decision": decision.get("decision"),
            "allowed": bool(decision.get("allowed")),
            "reason": reason,
        })

    @staticmethod
    def _operation_for(envelope: ActionEnvelope) -> str:
        values = " ".join([
            envelope.intent,
            envelope.plugin,
            " ".join(envelope.cleanup),
            json.dumps(envelope.normalized_params, ensure_ascii=False, sort_keys=True, default=str),
        ]).lower()
        if any(word in values for word in ("persist", "crontab", "systemd", "startup", "autorun")):
            return "persistence"
        if any(word in values for word in ("dos", "flood", "stress", "logclear", "clear logs", "truncate log")):
            return "denial_of_service" if any(word in values for word in ("dos", "flood", "stress")) else "log_clearing"
        if any(word in values for word in ("upload", "write file", "file_write")):
            return "upload" if "upload" in values else "destructive_write"
        if any(word in values for word in ("lateral", "pivot", "scope expansion", "proxy target")):
            return "scope_expansion"
        return ""

    def authorize_action(self, envelope: ActionEnvelope, contract: ScopeContract, token: str, *, now: datetime | None = None) -> PolicyDecision:
        with self._lock:
            try:
                token_payload = self.verify_token(token, contract, now=now)
            except ScopeTokenError as exc:
                decision = PolicyDecision(allowed=False, decision=PolicyDecisionKind.DENY.value, reason=str(exc), policy_version=contract.policy_version, scope_id=contract.scope_id)
                self._record_audit(envelope, decision, reason=str(exc))
                return decision
            request_key = f"{contract.scope_id}:{envelope.idempotency_key}:{envelope.action_id}"
            cached = self._decision_cache.get(request_key)
            if cached is not None:
                replay = PolicyDecision(dict(cached, reason="idempotent replay"))
                self._record_audit(envelope, replay, reason="idempotent replay")
                return replay
            level = ActionLevel(envelope.action_level)
            protocol = envelope.protocol.lower().strip()
            task_id = envelope.task_id
            current = now or datetime.now(timezone.utc)
            reason = ""
            if self._emergency_stop or contract.emergency_stop:
                reason = "emergency stop is active"
            elif current < contract.starts_at or current >= contract.expires_at:
                reason = "scope time window is inactive"
            elif envelope.scope_id != contract.scope_id or token_payload.get("scope_id") != envelope.scope_id:
                reason = "scope id mismatch"
            elif envelope.mission_id not in {"mission-local", contract.mission_id}:
                reason = "mission id mismatch"
            elif level == ActionLevel.PROHIBITED or level in contract.forbidden_actions:
                reason = "action level is prohibited by policy"
            elif level not in contract.allowed_actions:
                reason = "action level is not allowed by scope"
            elif not self.target_in_scope(envelope.target, contract):
                reason = "target is outside scope"
            elif envelope.port is not None and not self.port_in_scope(envelope.port, contract):
                reason = "port is outside scope"
            elif protocol not in {item.lower() for item in contract.allowed_protocols}:
                reason = "protocol is outside scope"
            elif not envelope.expected_evidence:
                reason = "expected evidence is required"
            elif self._operation_for(envelope) == "persistence":
                reason = "persistence operation is forbidden"
            elif self._operation_for(envelope) == "destructive_write" and not contract.allow_uploads:
                reason = "destructive write is forbidden"
            elif self._operation_for(envelope) == "upload" and not contract.allow_uploads:
                reason = "upload is outside scope"
            elif level == ActionLevel.CREDENTIAL_TEST and not contract.allow_credentials:
                reason = "credential testing is not enabled"
            elif level in {ActionLevel.SESSION_VERIFY, ActionLevel.POST_VERIFY} and not contract.allow_sessions:
                reason = "session verification is not enabled"
            elif level == ActionLevel.POST_VERIFY and not contract.allow_privilege_validation:
                reason = "privilege validation is not enabled"
            elif self._commands.get(task_id, 0) >= contract.max_commands:
                reason = "command budget exhausted"
            elif self._requests.get(task_id, 0) >= contract.max_network_requests:
                reason = "network request budget exhausted"
            elif self._active.get(task_id, 0) >= contract.max_concurrency:
                reason = "concurrency budget exhausted"
            else:
                now_mono = time.monotonic()
                times = [stamp for stamp in self._request_times.get(task_id, []) if now_mono - stamp < 1.0]
                if len(times) >= contract.max_requests_per_second + contract.max_request_burst:
                    reason = "request rate budget exhausted"
                else:
                    self._request_times[task_id] = times + [now_mono]
            if reason:
                decision = PolicyDecision(allowed=False, decision=PolicyDecisionKind.DENY.value, reason=reason, policy_version=contract.policy_version, scope_id=contract.scope_id)
                self._record_audit(envelope, decision, reason=reason)
                return decision
            self._commands[task_id] = self._commands.get(task_id, 0) + 1
            self._requests[task_id] = self._requests.get(task_id, 0) + (1 if envelope.port is not None else 0)
            self._active[task_id] = self._active.get(task_id, 0) + 1
            limited = envelope.risk in {"high", "critical"} and str(contract.autonomy_mode) == "supervised"
            decision = PolicyDecision(
                allowed=True,
                decision=(PolicyDecisionKind.ALLOW_WITH_LIMITS.value if limited else PolicyDecisionKind.ALLOW.value),
                reason="authorized with limits" if limited else "authorized",
                policy_version=contract.policy_version,
                scope_id=contract.scope_id,
                token_id=token_payload.get("token_id", ""),
                limits={"max_duration_seconds": contract.max_duration_seconds} if limited else {},
            )
            self._record_audit(envelope, decision, reason=str(decision["reason"]))
            self._decision_cache[request_key] = PolicyDecision(decision)
            return decision
