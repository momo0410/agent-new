"""Task/plugin/model/Skill metrics and runtime health signals."""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

DIMENSIONS = ("task_id", "target", "plugin", "skill", "model", "version")


class MetricsAggregator:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._groups: dict[tuple[tuple[str, str], ...], dict[str, float]] = defaultdict(self._empty)

    @staticmethod
    def _empty() -> dict[str, float]:
        return {
            "runs": 0.0,
            "successes": 0.0,
            "failures": 0.0,
            "duration_seconds": 0.0,
            "cost": 0.0,
            "repeated_actions": 0.0,
            "security_events": 0.0,
        }

    @staticmethod
    def _dimensions(values: dict[str, Any]) -> tuple[tuple[str, str], ...]:
        return tuple((name, str(values.get(name, "unknown") or "unknown")[:240]) for name in DIMENSIONS)

    def observe(
        self,
        dimensions: dict[str, Any],
        *,
        success: bool,
        duration_seconds: float = 0.0,
        cost: float = 0.0,
        repeated_actions: int = 0,
        security_events: int = 0,
    ) -> None:
        key = self._dimensions(dimensions)
        with self._lock:
            bucket = self._groups[key]
            bucket["runs"] += 1
            bucket["successes"] += 1 if success else 0
            bucket["failures"] += 0 if success else 1
            bucket["duration_seconds"] += max(0.0, float(duration_seconds or 0.0))
            bucket["cost"] += max(0.0, float(cost or 0.0))
            bucket["repeated_actions"] += max(0, int(repeated_actions or 0))
            bucket["security_events"] += max(0, int(security_events or 0))

    def record_action(self, action: dict[str, Any], *, task_id: str = "") -> None:
        status = str(action.get("status", "")).lower()
        success = status in {"completed", "success", "succeeded", "verified"} and not action.get("error")
        self.observe(
            {
                "task_id": task_id or action.get("task_id", "unknown"),
                "target": action.get("target", action.get("surface", "unknown")),
                "plugin": action.get("tool", action.get("plugin", "unknown")),
                "skill": action.get("skill_id", action.get("skill", "unknown")),
                "model": action.get("model", "unknown"),
                "version": action.get("tool_version", action.get("version", "unknown")),
            },
            success=success,
            duration_seconds=float(action.get("duration_seconds", 0.0) or 0.0),
            cost=float(action.get("cost", action.get("token_cost", 0.0)) or 0.0),
            repeated_actions=int(action.get("repeated_actions", 0) or 0),
            security_events=int(action.get("security_events", 0) or 0),
        )

    def record_events(self, events: Iterable[dict[str, Any]], *, task_id: str = "") -> None:
        for event in events:
            payload = event.get("payload") if isinstance(event, dict) else {}
            payload = payload if isinstance(payload, dict) else {}
            event_type = str(event.get("event_type", ""))
            if event_type in {"policy.denied", "web.blocked", "process.orphan", "security.alert"}:
                self.observe(
                    {
                        "task_id": task_id,
                        "target": payload.get("target", payload.get("url", "unknown")),
                        "plugin": payload.get("plugin", event_type),
                        "skill": payload.get("skill", "unknown"),
                        "model": payload.get("model", "unknown"),
                        "version": payload.get("version", "unknown"),
                    },
                    success=False,
                    security_events=1,
                )

    def snapshot(self, *, group_by: Iterable[str] | None = None) -> dict[str, Any]:
        dimensions = tuple(name for name in (group_by or DIMENSIONS) if name in DIMENSIONS)
        with self._lock:
            result: dict[str, dict[str, float]] = {}
            for full_key, values in self._groups.items():
                full = dict(full_key)
                key = ",".join(f"{name}={full[name]}" for name in dimensions) or "all"
                bucket = result.setdefault(key, self._empty())
                for name, value in values.items():
                    bucket[name] += value
            for values in result.values():
                values["success_rate"] = values["successes"] / values["runs"] if values["runs"] else 1.0
                values["mean_duration_seconds"] = values["duration_seconds"] / values["runs"] if values["runs"] else 0.0
            return {
                "dimensions": list(dimensions),
                "groups": result,
                "generated_at": time.time(),
            }


class RuntimeHealthMonitor:
    """Collects isolation signals and emits a quarantine recommendation."""

    def __init__(self, *, disk_paths: Iterable[str | os.PathLike[str]] = ()) -> None:
        self._lock = threading.RLock()
        self._disk_paths = [Path(item) for item in disk_paths]
        self._disk_baseline = self._disk_size()
        self._long_connections = 0
        self._network_anomalies = 0
        self._alerts: list[dict[str, Any]] = []

    def record_connection(self, *, opened: bool, long_lived: bool = False) -> None:
        with self._lock:
            if long_lived:
                self._long_connections += 1 if opened else -1
                self._long_connections = max(0, self._long_connections)

    def record_network(self, *, anomalous: bool, reason: str = "") -> None:
        with self._lock:
            if anomalous:
                self._network_anomalies += 1
                self._alerts.append({"kind": "network", "reason": str(reason)[:500], "at": time.time()})

    def inspect(
        self,
        *,
        process_count: int = 0,
        budget_usage: dict[str, Any] | None = None,
        budget_limits: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            disk_size = self._disk_size()
            growth = max(0, disk_size - self._disk_baseline)
            alerts = list(self._alerts)
            if process_count > 0:
                alerts.append({"kind": "process", "reason": "supervised children are still active"})
            if self._long_connections > 0:
                alerts.append({"kind": "connection", "reason": "long-lived connections remain"})
            if budget_usage and budget_limits:
                for key, limit in budget_limits.items():
                    if isinstance(limit, (int, float)) and float(budget_usage.get(key, 0)) > float(limit):
                        alerts.append({"kind": "budget", "reason": f"{key} exceeded"})
            if growth > 0:
                alerts.append({"kind": "disk", "reason": f"disk grew by {growth} bytes"})
            return {
                "healthy": not alerts,
                "quarantine": bool(alerts),
                "alerts": alerts[-100:],
                "disk_bytes": disk_size,
                "disk_growth_bytes": growth,
                "long_connections": self._long_connections,
                "network_anomalies": self._network_anomalies,
            }

    def _disk_size(self) -> int:
        total = 0
        for path in self._disk_paths:
            if path.is_file():
                total += path.stat().st_size
            elif path.is_dir():
                total += sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
        return total


__all__ = ["MetricsAggregator", "RuntimeHealthMonitor", "DIMENSIONS"]
