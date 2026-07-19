from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .contracts import EventEnvelope, utc_now
from .event_schema import EVENT_SCHEMA_VERSION, timeline_entry


class EventStoreCorruptionError(RuntimeError):
    """Raised when an append-only event chain is malformed or tampered with."""


# Backward-compatible name for callers that used the initial API.
EventStoreCorruption = EventStoreCorruptionError


class EventStore:
    """Small JSONL event store with a hash chain and deterministic replay."""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _canonical(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")

    def _tail(self) -> tuple[int, str]:
        if not self.path.exists():
            return 0, ""
        sequence, event_hash = 0, ""
        with self.path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise EventStoreCorruption(f"invalid event JSON at {self.path}") from exc
                sequence = int(raw.get("sequence", 0))
                event_hash = str(raw.get("event_hash", ""))
        return sequence, event_hash

    def append(
        self,
        task_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        actor: str = "system",
        previous_state: str | None = None,
        new_state: str | None = None,
        reason: str = "",
        rule_version: str = "",
        evidence_refs: list[str] | None = None,
        idempotency_key: str = "",
    ) -> EventEnvelope:
        with self._lock:
            if idempotency_key:
                for existing in self.read(verify=True):
                    if existing.idempotency_key == idempotency_key:
                        return existing
            previous_sequence, previous_hash = self._tail()
            event = EventEnvelope(
                schema_version=EVENT_SCHEMA_VERSION,
                task_id=task_id,
                sequence=previous_sequence + 1,
                timestamp=utc_now(),
                event_type=event_type,
                actor=actor,
                payload=payload or {},
                previous_state=previous_state,
                new_state=new_state,
                reason=reason,
                rule_version=rule_version,
                evidence_refs=evidence_refs or [],
                idempotency_key=idempotency_key,
                previous_hash=previous_hash,
            )
            unsigned = event.model_dump(mode="json")
            unsigned["event_hash"] = ""
            event_hash = hashlib.sha256((previous_hash + "\n").encode("utf-8") + self._canonical(unsigned)).hexdigest()
            event = event.model_copy(update={"event_hash": event_hash})
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            return event

    def append_many(self, task_id: str, events: list[dict[str, Any]], *, actor: str = "system") -> list[EventEnvelope]:
        """Append a deterministic batch under the same process lock."""
        appended: list[EventEnvelope] = []
        with self._lock:
            for item in events:
                appended.append(self.append(
                    task_id,
                    str(item["event_type"]),
                    dict(item.get("payload") or {}),
                    actor=str(item.get("actor") or actor),
                    previous_state=item.get("previous_state"),
                    new_state=item.get("new_state"),
                    reason=str(item.get("reason") or ""),
                    rule_version=str(item.get("rule_version") or ""),
                    evidence_refs=list(item.get("evidence_refs") or []),
                    idempotency_key=str(item.get("idempotency_key") or ""),
                ))
        return appended

    def read(self, *, verify: bool = True) -> list[EventEnvelope]:
        with self._lock:
            if not self.path.exists():
                return []
            events: list[EventEnvelope] = []
            previous_hash = ""
            expected_sequence = 1
            with self.path.open("r", encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    try:
                        raw = json.loads(line)
                        event = EventEnvelope.model_validate(raw)
                    except (json.JSONDecodeError, ValueError) as exc:
                        raise EventStoreCorruption(f"invalid event at sequence {expected_sequence}") from exc
                    if verify:
                        unsigned = event.model_dump(mode="json")
                        stored_hash = unsigned.pop("event_hash", "")
                        unsigned["event_hash"] = ""
                        computed = hashlib.sha256((previous_hash + "\n").encode("utf-8") + self._canonical(unsigned)).hexdigest()
                        if event.sequence != expected_sequence or event.previous_hash != previous_hash or stored_hash != computed:
                            raise EventStoreCorruption(f"event chain mismatch at sequence {event.sequence}")
                    events.append(event)
                    previous_hash = event.event_hash
                    expected_sequence += 1
            return events

    def replay(self, projector: Callable[[dict[str, Any], EventEnvelope], dict[str, Any]], initial: dict[str, Any] | None = None) -> dict[str, Any]:
        state = dict(initial or {})
        for event in self.read(verify=True):
            state = projector(state, event)
        return state

    def stream(self, *, task_id: str | None = None, after_sequence: int = 0, verify: bool = True) -> list[EventEnvelope]:
        return [
            event for event in self.read(verify=verify)
            if event.sequence > after_sequence and (task_id is None or event.task_id == task_id)
        ]

    def integrity_manifest(self) -> dict[str, Any]:
        verified = self.verify()
        return {
            "schema_version": "event-manifest.v1",
            "path": self.path.name,
            "event_count": verified["event_count"],
            "last_hash": verified["last_hash"],
            "sealed": True,
        }

    def verify(self) -> dict[str, Any]:
        events = self.read(verify=True)
        return {"valid": True, "event_count": len(events), "last_hash": events[-1].event_hash if events else ""}


class EventProjectorRegistry:
    """Versioned event fold handlers used to rebuild read models."""

    def __init__(self):
        self._handlers: dict[str, Callable[[dict[str, Any], EventEnvelope], dict[str, Any]]] = {}

    def register(self, event_type: str, handler: Callable[[dict[str, Any], EventEnvelope], dict[str, Any]]) -> None:
        key = str(event_type).strip()
        if not key or key in self._handlers:
            raise ValueError(f"duplicate projector: {key}")
        self._handlers[key] = handler

    def project(self, state: dict[str, Any], event: EventEnvelope) -> dict[str, Any]:
        timeline = state.setdefault("timeline", [])
        entry = timeline_entry(event)
        if not any(
            isinstance(item, dict) and str(item.get("event_id", "")) == event.event_id
            for item in timeline
        ):
            timeline.append(entry)
        state["timeline"] = timeline[-1000:]
        handler = self._handlers.get(event.event_type)
        if handler is None:
            projected = dict(state)
            projected.setdefault("unhandled_events", []).append(event.event_type)
            projected["sequence"] = event.sequence
            return projected
        projected = handler(dict(state), event)
        projected["sequence"] = event.sequence
        projected["last_event_id"] = event.event_id
        return projected

    def rebuild(self, store: EventStore, *, initial: dict[str, Any] | None = None) -> dict[str, Any]:
        return store.replay(self.project, initial)
