"""Immutable observation records linking raw tool output to versioned parsers."""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ConfigDict, Field

from .contracts import ContractModel

_SENSITIVE_KEYS = ("password", "secret", "token", "api_key", "private_key", "cookie", "session_key")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: str | bytes) -> str:
    encoded = value if isinstance(value, bytes) else value.encode("utf-8", errors="replace")
    return hashlib.sha256(encoded).hexdigest()


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]"
            if any(marker in str(key).lower() for marker in _SENSITIVE_KEYS)
            else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_redact(item) for item in value]
    return value


class ObservationRecord(ContractModel):
    """Fact-layer record; raw content stays in its evidence storage location."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True, frozen=True)

    schema_version: str = "observation.v1"
    observation_id: str = Field(min_length=8, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=512)
    source: str = Field(min_length=1, max_length=160)
    source_version: str = Field(default="unknown", max_length=240)
    raw_ref: str = Field(min_length=1, max_length=1024)
    raw_hash: str = Field(min_length=64, max_length=64)
    raw_size: int = Field(default=0, ge=0)
    parser: str = Field(min_length=1, max_length=160)
    parser_version: str = Field(min_length=1, max_length=128)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    action_id: str = Field(default="", max_length=160)
    event_refs: list[str] = Field(default_factory=list)
    facts: Any = Field(default_factory=list)
    status: str = Field(default="observed", max_length=80)
    returncode: int | None = None
    command_hash: str = Field(default="", max_length=128)
    environment_fingerprint: dict[str, Any] = Field(default_factory=dict)
    parent_observation_id: str = Field(default="", max_length=128)
    integrity_hash: str = Field(min_length=64, max_length=64)

    @classmethod
    def create(
        cls,
        *,
        task_id: str,
        target: str,
        source: str,
        raw_output: str | bytes,
        raw_ref: str,
        parser: str,
        parser_version: str,
        facts: Any = None,
        source_version: str = "unknown",
        action_id: str = "",
        event_refs: list[str] | None = None,
        status: str = "observed",
        returncode: int | None = None,
        command_hash: str = "",
        environment_fingerprint: dict[str, Any] | None = None,
        parent_observation_id: str = "",
        observed_at: datetime | None = None,
    ) -> ObservationRecord:
        raw_bytes = raw_output if isinstance(raw_output, bytes) else str(raw_output).encode("utf-8", errors="replace")
        raw_hash = _hash(raw_bytes)
        identity = _canonical({
            "task_id": task_id,
            "target": target,
            "source": source,
            "raw_hash": raw_hash,
            "parser": parser,
            "parser_version": parser_version,
            "action_id": action_id,
            "parent": parent_observation_id,
        })
        observation_id = "obs_" + _hash(identity)[:32]
        payload = {
            "schema_version": "observation.v1",
            "observation_id": observation_id,
            "task_id": str(task_id),
            "target": str(target),
            "source": str(source),
            "source_version": str(source_version or "unknown"),
            "raw_ref": str(raw_ref),
            "raw_hash": raw_hash,
            "raw_size": len(raw_bytes),
            "parser": str(parser),
            "parser_version": str(parser_version),
            "observed_at": observed_at or datetime.now(timezone.utc),
            "action_id": str(action_id),
            "event_refs": list(dict.fromkeys(str(item) for item in (event_refs or []) if str(item))),
            "facts": _redact(facts if facts is not None else []),
            "status": str(status or "observed"),
            "returncode": returncode,
            "command_hash": str(command_hash),
            "environment_fingerprint": _redact(environment_fingerprint or {}),
            "parent_observation_id": str(parent_observation_id),
        }
        payload["integrity_hash"] = _hash(_canonical(payload))
        return cls.model_validate(payload)

    def verify_integrity(self) -> bool:
        payload = self.model_dump(mode="python")
        stored = str(payload.pop("integrity_hash", ""))
        return stored == _hash(_canonical(payload))


# Short product-language alias used by schema consumers.
Observation = ObservationRecord


class ObservationStore:
    """Append-only, idempotent observation manifest with optional JSONL persistence."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else None
        self._lock = threading.RLock()
        self._records: list[ObservationRecord] = []
        self._by_id: dict[str, ObservationRecord] = {}
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    record = ObservationRecord.model_validate_json(line)
                except ValueError as exc:
                    raise ValueError(f"invalid observation at line {line_number}") from exc
                if not record.verify_integrity():
                    raise ValueError(f"observation integrity mismatch at line {line_number}")
                if record.observation_id not in self._by_id:
                    self._records.append(record)
                    self._by_id[record.observation_id] = record

    def append(self, record: ObservationRecord | dict[str, Any]) -> ObservationRecord:
        parsed = record if isinstance(record, ObservationRecord) else ObservationRecord.model_validate(record)
        if not parsed.verify_integrity():
            raise ValueError("observation integrity mismatch")
        with self._lock:
            existing = self._by_id.get(parsed.observation_id)
            if existing is not None:
                return existing
            if self.path is not None:
                with self.path.open("a", encoding="utf-8") as stream:
                    stream.write(parsed.model_dump_json() + "\n")
                    stream.flush()
            self._records.append(parsed)
            self._by_id[parsed.observation_id] = parsed
            return parsed

    add = append
    record = append

    def get(self, observation_id: str) -> ObservationRecord | None:
        return self._by_id.get(str(observation_id))

    def list(self, *, target: str | None = None, source: str | None = None) -> list[ObservationRecord]:
        return [
            record
            for record in self._records
            if (target is None or record.target == target)
            and (source is None or record.source == source)
        ]

    def verify(self) -> dict[str, Any]:
        invalid = [record.observation_id for record in self._records if not record.verify_integrity()]
        return {
            "valid": not invalid,
            "observation_count": len(self._records),
            "invalid_observation_ids": invalid,
            "manifest_hash": _hash(_canonical([record.integrity_hash for record in self._records])),
        }

    def replay(
        self,
        observation_id: str,
        *,
        raw_loader: Callable[[str], str | bytes],
        parser: Callable[[str], Any],
        parser_name: str,
        parser_version: str,
    ) -> ObservationRecord:
        previous = self.get(observation_id)
        if previous is None:
            raise KeyError(observation_id)
        raw = raw_loader(previous.raw_ref)
        raw_bytes = raw if isinstance(raw, bytes) else str(raw).encode("utf-8", errors="replace")
        if _hash(raw_bytes) != previous.raw_hash:
            raise ValueError("raw observation hash mismatch")
        text = raw_bytes.decode("utf-8", errors="replace")
        replayed = ObservationRecord.create(
            task_id=previous.task_id,
            target=previous.target,
            source=previous.source,
            source_version=previous.source_version,
            raw_output=raw_bytes,
            raw_ref=previous.raw_ref,
            parser=parser_name,
            parser_version=parser_version,
            facts=parser(text),
            action_id=previous.action_id,
            event_refs=previous.event_refs,
            status=previous.status,
            returncode=previous.returncode,
            command_hash=previous.command_hash,
            environment_fingerprint=previous.environment_fingerprint,
            parent_observation_id=previous.observation_id,
        )
        return self.append(replayed)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "observation-manifest.v1",
            "records": [record.model_dump(mode="json") for record in self._records],
            "integrity": self.verify(),
        }


__all__ = ["Observation", "ObservationRecord", "ObservationStore"]
