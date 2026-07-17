from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .contracts import EventEnvelope, utc_now


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

    def append(self, task_id: str, event_type: str, payload: dict[str, Any] | None = None, *, actor: str = "system") -> EventEnvelope:
        with self._lock:
            previous_sequence, previous_hash = self._tail()
            event = EventEnvelope(
                task_id=task_id,
                sequence=previous_sequence + 1,
                timestamp=utc_now(),
                event_type=event_type,
                actor=actor,
                payload=payload or {},
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

    def verify(self) -> dict[str, Any]:
        events = self.read(verify=True)
        return {"valid": True, "event_count": len(events), "last_hash": events[-1].event_hash if events else ""}
