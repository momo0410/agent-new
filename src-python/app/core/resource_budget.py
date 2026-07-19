"""Per-task resource accounting used by planners and execution adapters."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BudgetLimits:
    duration_seconds: float = 3600.0
    llm_tokens: int = 120000
    commands: int = 1000
    network_requests: int = 10000
    bruteforce_attempts: int = 100
    storage_bytes: int = 268435456
    concurrency: int = 1


@dataclass
class BudgetUsage:
    started_at: float = field(default_factory=time.monotonic)
    llm_tokens: int = 0
    commands: int = 0
    network_requests: int = 0
    bruteforce_attempts: int = 0
    storage_bytes: int = 0
    active: int = 0
    exhausted_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "elapsed_seconds": max(0.0, time.monotonic() - self.started_at),
            "llm_tokens": self.llm_tokens,
            "commands": self.commands,
            "network_requests": self.network_requests,
            "bruteforce_attempts": self.bruteforce_attempts,
            "storage_bytes": self.storage_bytes,
            "active": self.active,
            "exhausted_reason": self.exhausted_reason,
        }


class BudgetExceededError(RuntimeError):
    """Raised when a reservation would cross a task budget."""


BudgetExceeded = BudgetExceededError


class BudgetManager:
    """Atomic reservations; callers release concurrency in a finally block."""

    def __init__(self, limits: BudgetLimits | None = None):
        self.limits = limits or BudgetLimits()
        self._usage: dict[str, BudgetUsage] = {}
        self._lock = threading.RLock()

    def _get(self, task_id: str) -> BudgetUsage:
        return self._usage.setdefault(str(task_id), BudgetUsage())

    def reserve(self, task_id: str, *, commands: int = 0, network_requests: int = 0, llm_tokens: int = 0, bruteforce_attempts: int = 0, storage_bytes: int = 0, concurrency: int = 0) -> BudgetUsage:
        with self._lock:
            usage = self._get(task_id)
            checks = (
                ("duration budget exhausted", time.monotonic() - usage.started_at >= self.limits.duration_seconds),
                ("command budget exhausted", usage.commands + commands > self.limits.commands),
                ("network request budget exhausted", usage.network_requests + network_requests > self.limits.network_requests),
                ("LLM token budget exhausted", usage.llm_tokens + llm_tokens > self.limits.llm_tokens),
                ("bruteforce budget exhausted", usage.bruteforce_attempts + bruteforce_attempts > self.limits.bruteforce_attempts),
                ("storage budget exhausted", usage.storage_bytes + storage_bytes > self.limits.storage_bytes),
                ("concurrency budget exhausted", usage.active + concurrency > self.limits.concurrency),
            )
            for reason, exceeded in checks:
                if exceeded:
                    usage.exhausted_reason = reason
                    raise BudgetExceeded(reason)
            usage.commands += max(0, commands)
            usage.network_requests += max(0, network_requests)
            usage.llm_tokens += max(0, llm_tokens)
            usage.bruteforce_attempts += max(0, bruteforce_attempts)
            usage.storage_bytes += max(0, storage_bytes)
            usage.active += max(0, concurrency)
            return usage

    def release_concurrency(self, task_id: str, amount: int = 1) -> None:
        with self._lock:
            usage = self._get(task_id)
            usage.active = max(0, usage.active - max(0, amount))

    def usage(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            return self._get(task_id).as_dict()

    def reset(self, task_id: str) -> None:
        with self._lock:
            self._usage.pop(str(task_id), None)
