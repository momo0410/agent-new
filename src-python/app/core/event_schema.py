"""Shared event-envelope helpers used by the JSON state and read models."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

EVENT_SCHEMA_VERSION = "event.v1"
MAX_STRING_LENGTH = 2000
MAX_COLLECTION_ITEMS = 100

_SENSITIVE_KEYS = {
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "privatekey",
    "authorization",
    "cookie",
    "full_stdout",
    "stderr_raw",
}


def redact_payload(value: Any, *, key: str = "") -> Any:
    """Return JSON-safe, bounded payload data while retaining useful structure."""
    normalized_key = key.lower().replace("-", "_")
    if normalized_key in _SENSITIVE_KEYS or any(
        marker in normalized_key for marker in ("api_key", "private_key", "password")
    ):
        return "[REDACTED]"
    if isinstance(value, str):
        return value[:MAX_STRING_LENGTH]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return {
            str(item_key): redact_payload(item_value, key=str(item_key))
            for item_key, item_value in list(value.items())[:MAX_COLLECTION_ITEMS]
        }
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [redact_payload(item, key=key) for item in list(value)[:MAX_COLLECTION_ITEMS]]
    return str(value)[:MAX_STRING_LENGTH]


def redact_event_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(redact_payload(dict(payload or {})))


def timeline_entry(event: Any) -> dict[str, Any]:
    """Build the bounded, public timeline representation for an event."""
    return {
        "event_id": str(getattr(event, "event_id", "")),
        "schema_version": str(getattr(event, "schema_version", EVENT_SCHEMA_VERSION)),
        "sequence": int(getattr(event, "sequence", 0) or 0),
        "timestamp": getattr(getattr(event, "timestamp", None), "isoformat", lambda: str(getattr(event, "timestamp", "")))(),
        "event_type": str(getattr(event, "event_type", "")),
        "actor": str(getattr(event, "actor", "system")),
        "reason": str(getattr(event, "reason", "") or ""),
        "previous_state": getattr(event, "previous_state", None),
        "new_state": getattr(event, "new_state", None),
        "evidence_refs": [str(item) for item in list(getattr(event, "evidence_refs", []) or [])[:100]],
        "payload": redact_event_payload(getattr(event, "payload", {}) or {}),
    }
