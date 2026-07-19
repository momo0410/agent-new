"""Thread-safe mission lifecycle control shared by API, agent and executor."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

StopCallback = Callable[[], None]
TransitionListener = Callable[[str, str, dict[str, Any]], None]


class MissionControl:
    """Coordinate pause, resume and cooperative cancellation across threads.

    ``cancel_event`` is intentionally public: process supervisors and blocking
    execution adapters can share the same signal without an extra polling
    bridge.  Lifecycle callbacks are invoked outside the internal lock.
    """

    TERMINAL_STATUSES = frozenset({"cancelled", "completed", "failed"})

    def __init__(self, mission_id: str = "") -> None:
        now = self._now()
        self.mission_id = str(mission_id or uuid4().hex)[:128]
        self.cancel_event = threading.Event()
        self._runnable_event = threading.Event()
        self._runnable_event.set()
        self._lock = threading.RLock()
        self._status = "running"
        self._reason = ""
        self._created_at = now
        self._updated_at = now
        self._paused_at = ""
        self._finished_at = ""
        self._stop_callbacks: dict[str, StopCallback] = {}
        self._listeners: dict[str, TransitionListener] = {}
        self._callback_errors: list[str] = []

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason

    @property
    def is_cancel_requested(self) -> bool:
        return self.cancel_event.is_set()

    @property
    def is_terminal(self) -> bool:
        with self._lock:
            return self._status in self.TERMINAL_STATUSES

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "mission_id": self.mission_id,
                "status": self._status,
                "canonical_status": self._status.upper(),
                "reason": self._reason,
                "paused": self._status == "paused",
                "cancel_requested": self.cancel_event.is_set(),
                "created_at": self._created_at,
                "updated_at": self._updated_at,
                "paused_at": self._paused_at,
                "finished_at": self._finished_at,
                "callback_errors": list(self._callback_errors),
            }

    def register_stop_callback(self, callback: StopCallback) -> str:
        if not callable(callback):
            raise TypeError("stop callback must be callable")
        token = uuid4().hex
        invoke_now = False
        with self._lock:
            self._stop_callbacks[token] = callback
            invoke_now = self.cancel_event.is_set()
        if invoke_now:
            self._invoke_callback(callback)
        return token

    def unregister_stop_callback(self, token: str) -> None:
        with self._lock:
            self._stop_callbacks.pop(str(token), None)

    def register_listener(self, listener: TransitionListener) -> str:
        if not callable(listener):
            raise TypeError("transition listener must be callable")
        token = uuid4().hex
        with self._lock:
            self._listeners[token] = listener
        return token

    def unregister_listener(self, token: str) -> None:
        with self._lock:
            self._listeners.pop(str(token), None)

    def pause(self, reason: str = "") -> bool:
        with self._lock:
            if self._status != "running" or self.cancel_event.is_set():
                return False
            previous = self._status
            self._status = "paused"
            self._reason = str(reason or "mission paused")[:1000]
            self._paused_at = self._now()
            self._updated_at = self._paused_at
            self._runnable_event.clear()
            listeners = list(self._listeners.values())
            snapshot = self.snapshot()
        self._notify(listeners, previous, "paused", snapshot)
        return True

    def resume(self, reason: str = "") -> bool:
        with self._lock:
            if self._status != "paused" or self.cancel_event.is_set():
                return False
            previous = self._status
            self._status = "running"
            self._reason = str(reason or "mission resumed")[:1000]
            self._updated_at = self._now()
            self._runnable_event.set()
            listeners = list(self._listeners.values())
            snapshot = self.snapshot()
        self._notify(listeners, previous, "running", snapshot)
        return True

    def cancel(self, reason: str = "") -> bool:
        with self._lock:
            if self._status in self.TERMINAL_STATUSES or self.cancel_event.is_set():
                return False
            previous = self._status
            self._status = "cancelling"
            self._reason = str(reason or "mission cancellation requested")[:1000]
            self._updated_at = self._now()
            self.cancel_event.set()
            self._runnable_event.set()
            listeners = list(self._listeners.values())
            callbacks = list(self._stop_callbacks.values())
            snapshot = self.snapshot()
        self._notify(listeners, previous, "cancelling", snapshot)
        for callback in callbacks:
            self._invoke_callback(callback)
        return True

    def wait_until_runnable(self, poll_interval: float = 0.1) -> bool:
        """Block while paused and return whether work should proceed."""
        timeout = max(0.01, float(poll_interval))
        while not self.cancel_event.is_set():
            if self._runnable_event.wait(timeout=timeout):
                return not self.cancel_event.is_set()
        return False

    def mark_cancelled(self, reason: str = "") -> bool:
        return self._mark_terminal("cancelled", reason or self.reason or "mission cancelled")

    def mark_completed(self, reason: str = "") -> bool:
        if self.cancel_event.is_set():
            return self.mark_cancelled(reason)
        return self._mark_terminal("completed", reason or "mission completed")

    def mark_failed(self, reason: str = "") -> bool:
        if self.cancel_event.is_set():
            return self.mark_cancelled(reason)
        return self._mark_terminal("failed", reason or "mission failed")

    def _mark_terminal(self, status: str, reason: str) -> bool:
        with self._lock:
            if self._status in self.TERMINAL_STATUSES:
                return self._status == status
            previous = self._status
            self._status = status
            self._reason = str(reason)[:1000]
            self._updated_at = self._now()
            self._finished_at = self._updated_at
            self._runnable_event.set()
            if status == "cancelled":
                self.cancel_event.set()
            listeners = list(self._listeners.values())
            snapshot = self.snapshot()
        self._notify(listeners, previous, status, snapshot)
        return True

    def _invoke_callback(self, callback: StopCallback) -> None:
        try:
            callback()
        except Exception as exc:  # pragma: no cover - callback ownership is external
            with self._lock:
                self._callback_errors.append(f"{type(exc).__name__}: {exc}"[:500])
                self._callback_errors = self._callback_errors[-20:]

    def _notify(
        self,
        listeners: list[TransitionListener],
        previous: str,
        current: str,
        snapshot: dict[str, Any],
    ) -> None:
        for listener in listeners:
            try:
                listener(previous, current, dict(snapshot))
            except Exception as exc:  # pragma: no cover - listener ownership is external
                with self._lock:
                    self._callback_errors.append(f"{type(exc).__name__}: {exc}"[:500])
                    self._callback_errors = self._callback_errors[-20:]
