"""Append-only security audit records with tamper-evident chaining."""
from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any, Literal


AuditLevel = Literal["user_visible", "debug", "security_audit", "sensitive_evidence"]
AUDIT_LEVELS: tuple[str, ...] = (
    "user_visible",
    "debug",
    "security_audit",
    "sensitive_evidence",
)
_ROLE_LEVELS: dict[str, frozenset[str]] = {
    "student": frozenset({"user_visible"}),
    "operator": frozenset({"user_visible", "debug"}),
    "teacher": frozenset({"user_visible", "debug", "security_audit"}),
    "course_admin": frozenset({"user_visible", "debug", "security_audit"}),
    "security_admin": frozenset(AUDIT_LEVELS),
    "administrator": frozenset(AUDIT_LEVELS),
    "system": frozenset(AUDIT_LEVELS),
}
_SECRET_KEYS = {
    "password", "passwd", "secret", "token", "api_key", "private_key",
    "access_token", "refresh_token", "cookie", "authorization",
}


class AuditLog:
    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _hash(previous: str, payload: dict[str, Any]) -> str:
        canonical = dict(payload)
        canonical.pop("event_hash", None)
        body = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256((previous + "\n" + body).encode()).hexdigest()

    def append(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        actor: str = "system",
        level: AuditLevel = "security_audit",
    ) -> dict[str, Any]:
        normalized_level = str(level).strip().lower()
        if normalized_level not in AUDIT_LEVELS:
            raise ValueError(f"unknown audit level: {level}")
        with self._lock:
            previous = ""
            sequence = 1
            if self.path.exists():
                for line in self.path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        prior = json.loads(line)
                        previous = str(prior.get("event_hash", ""))
                        sequence = int(prior.get("sequence", 0)) + 1
            record = {
                "sequence": sequence,
                "event_type": str(event_type),
                "actor": str(actor),
                "level": normalized_level,
                "payload": self._redact_payload(payload, sensitive=normalized_level == "sensitive_evidence"),
                "previous_hash": previous,
            }
            record["event_hash"] = self._hash(previous, record)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            return record

    @classmethod
    def _redact_payload(cls, payload: dict[str, Any], *, sensitive: bool) -> dict[str, Any]:
        if not sensitive:
            return dict(payload)

        def scrub(value: Any, key: str = "") -> Any:
            if key.lower() in _SECRET_KEYS or any(marker in key.lower() for marker in ("password", "token", "secret", "private_key")):
                raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
                return {"redacted": True, "digest": hashlib.sha256(raw.encode("utf-8")).hexdigest()}
            if isinstance(value, dict):
                return {str(child_key): scrub(child_value, str(child_key)) for child_key, child_value in value.items()}
            if isinstance(value, list):
                return [scrub(item, key) for item in value]
            return value

        return {str(key): scrub(value, str(key)) for key, value in payload.items()}

    def read(self, *, verify: bool = True) -> list[dict[str, Any]]:
        with self._lock:
            records: list[dict[str, Any]] = []
            previous = ""
            expected = 1
            if not self.path.exists():
                return records
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                if verify and (int(record.get("sequence", 0)) != expected or record.get("previous_hash", "") != previous):
                    raise ValueError("audit chain sequence mismatch")
                stored = record.get("event_hash", "")
                if verify:
                    unsigned = dict(record)
                    unsigned["event_hash"] = stored
                    if self._hash(previous, unsigned) != stored:
                        raise ValueError("audit chain hash mismatch")
                records.append(record)
                previous = str(stored)
                expected += 1
            return records

    @staticmethod
    def levels_for_role(actor_role: str) -> frozenset[str]:
        return _ROLE_LEVELS.get(str(actor_role or "").strip().lower(), frozenset())

    def read_for(self, actor_role: str, *, verify: bool = True) -> list[dict[str, Any]]:
        """Return only records visible to the supplied role."""
        allowed = self.levels_for_role(actor_role)
        return [record for record in self.read(verify=verify) if str(record.get("level", "security_audit")) in allowed]

    def read_level(self, level: AuditLevel, *, verify: bool = True) -> list[dict[str, Any]]:
        normalized = str(level).strip().lower()
        if normalized not in AUDIT_LEVELS:
            raise ValueError(f"unknown audit level: {level}")
        return [record for record in self.read(verify=verify) if record.get("level") == normalized]
