from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import secrets
from datetime import datetime, timedelta, timezone
from fnmatch import fnmatch
from typing import Any

from .contracts import ActionEnvelope, ActionLevel, ScopeContract


class ScopeTokenError(ValueError):
    pass


class PolicyDecision(dict):
    """JSON-compatible decision object kept intentionally small for audit logs."""

    @property
    def allowed(self) -> bool:
        return bool(self.get("allowed"))


class ScopePolicy:
    def __init__(self, secret: bytes | None = None, *, token_ttl_seconds: int = 900):
        self._secret = secret or secrets.token_bytes(32)
        self.token_ttl_seconds = max(60, min(token_ttl_seconds, 86400))

    @staticmethod
    def _contract_hash(contract: ScopeContract) -> str:
        body = contract.model_dump(mode="json")
        return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def issue_token(self, contract: ScopeContract, *, now: datetime | None = None) -> str:
        current = now or datetime.now(timezone.utc)
        if contract.expires_at <= current:
            raise ScopeTokenError("scope contract expired")
        payload = {
            "token_id": secrets.token_urlsafe(12),
            "scope_id": contract.scope_id,
            "contract_hash": self._contract_hash(contract),
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
            if payload.get("scope_id") != contract.scope_id or payload.get("contract_hash") != self._contract_hash(contract):
                raise ScopeTokenError("scope token does not match contract")
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
            if candidate == normalized or candidate.endswith("." + normalized) or fnmatch(candidate, normalized):
                return True
        return False

    @staticmethod
    def port_in_scope(port: int | None, contract: ScopeContract) -> bool:
        if port is None:
            return True
        if port in contract.allowed_ports:
            return True
        return any(item.contains(port) for item in contract.allowed_port_ranges)

    def authorize_action(self, envelope: ActionEnvelope, contract: ScopeContract, token: str, *, now: datetime | None = None) -> PolicyDecision:
        try:
            token_payload = self.verify_token(token, contract, now=now)
        except ScopeTokenError as exc:
            return PolicyDecision(allowed=False, reason=str(exc), policy_version=contract.policy_version, scope_id=contract.scope_id)
        level = ActionLevel(envelope.action_level)
        protocol = envelope.protocol.lower().strip()
        if envelope.scope_id != contract.scope_id or token_payload.get("scope_id") != envelope.scope_id:
            reason = "scope id mismatch"
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
        else:
            return PolicyDecision(
                allowed=True,
                reason="authorized",
                policy_version=contract.policy_version,
                scope_id=contract.scope_id,
                token_id=token_payload.get("token_id", ""),
            )
        return PolicyDecision(allowed=False, reason=reason, policy_version=contract.policy_version, scope_id=contract.scope_id)

