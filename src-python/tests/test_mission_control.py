from __future__ import annotations

import threading
import time

from app.core.mission_control import MissionControl


def test_pause_resume_controls_worker_progress():
    control = MissionControl("mission-1")
    assert control.pause("operator pause")
    entered = threading.Event()
    progressed = threading.Event()

    def worker() -> None:
        entered.set()
        if control.wait_until_runnable():
            progressed.set()

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(1)
    time.sleep(0.03)
    assert not progressed.is_set()
    assert control.resume()
    thread.join(1)
    assert progressed.is_set()
    assert control.status == "running"


def test_cancel_releases_pause_and_invokes_stop_callback():
    control = MissionControl("mission-2")
    control.pause()
    stopped = threading.Event()
    transitions: list[tuple[str, str]] = []
    control.register_stop_callback(stopped.set)
    control.register_listener(lambda previous, current, _snapshot: transitions.append((previous, current)))

    assert control.cancel("operator stop")
    assert stopped.is_set()
    assert control.wait_until_runnable() is False
    assert control.mark_cancelled()
    assert control.status == "cancelled"
    assert ("paused", "cancelling") in transitions
    assert ("cancelling", "cancelled") in transitions


def test_terminal_state_is_idempotent():
    control = MissionControl("mission-3")
    assert control.mark_completed()
    assert control.status == "completed"
    assert not control.cancel("late stop")
    assert not control.mark_failed("late failure")
