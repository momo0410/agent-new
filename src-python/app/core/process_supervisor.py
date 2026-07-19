"""Cancelable process-group execution with bounded output and dry-run support."""
from __future__ import annotations

import os
import shlex
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessLimits:
    timeout_seconds: float = 60.0
    max_output_bytes: int = 2_000_000
    kill_grace_seconds: float = 2.0


@dataclass
class ProcessResult:
    command: list[str] | str
    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    timed_out: bool = False
    cancelled: bool = False
    output_truncated: bool = False
    orphan_cleanup: str = "not_required"
    dry_run: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": self.duration_seconds,
            "timed_out": self.timed_out,
            "cancelled": self.cancelled,
            "output_truncated": self.output_truncated,
            "orphan_cleanup": self.orphan_cleanup,
            "dry_run": self.dry_run,
        }


class ProcessSupervisor:
    """One supervisor instance owns a kill switch for its task group."""

    def __init__(self, *, kill_switch: threading.Event | None = None):
        self.kill_switch = kill_switch or threading.Event()
        self._children: set[subprocess.Popen] = set()
        self._lock = threading.RLock()

    def stop(self) -> None:
        self.kill_switch.set()
        with self._lock:
            children = list(self._children)
        for child in children:
            self._terminate(child)

    def register(self, child: subprocess.Popen) -> None:
        """Register a process created by an adapter using custom I/O handling."""
        with self._lock:
            self._children.add(child)

    def unregister(self, child: subprocess.Popen) -> None:
        with self._lock:
            self._children.discard(child)

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for child in self._children if child.poll() is None)

    def run(
        self,
        command: Sequence[str] | str,
        *,
        limits: ProcessLimits | None = None,
        dry_run: bool = False,
        simulated_output: str = "",
        simulated_returncode: int = 0,
        shell: bool = False,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        on_output: Callable[[str, str], None] | None = None,
    ) -> ProcessResult:
        policy = limits or ProcessLimits()
        started = time.monotonic()
        command_value: list[str] | str = command if isinstance(command, str) else list(command)
        if dry_run:
            return ProcessResult(command=command_value, returncode=simulated_returncode, stdout=simulated_output, duration_seconds=0.0, dry_run=True)
        if self.kill_switch.is_set():
            return ProcessResult(command=command_value, returncode=None, cancelled=True, duration_seconds=0.0)

        process_command: list[str] | str = command_value
        if shell:
            command_text = command_value if isinstance(command_value, str) else shlex.join(command_value)
            process_command = (
                ["cmd.exe", "/d", "/s", "/c", command_text]
                if os.name == "nt"
                else ["/bin/sh", "-c", command_text]
            )

        child: subprocess.Popen | None = None
        cleanup = "not_required"
        try:
            if os.name == "nt":
                child = subprocess.Popen(
                    process_command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=cwd,
                    env=env,
                    text=False,
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                )
            else:
                child = subprocess.Popen(
                    process_command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=cwd,
                    env=env,
                    text=False,
                    start_new_session=True,
                )
            with self._lock:
                self._children.add(child)
            try:
                stdout_b, stderr_b = child.communicate(timeout=max(0.05, policy.timeout_seconds))
            except subprocess.TimeoutExpired as exc:
                cleanup = self._terminate(child)
                stdout_b, stderr_b = child.communicate()
                stdout_b = (exc.stdout or b"") + (stdout_b or b"")
                stderr_b = (exc.stderr or b"") + (stderr_b or b"")
                return self._result(command_value, child.returncode, stdout_b, stderr_b, started, policy, timed_out=True, cleanup=cleanup, on_output=on_output)
            if self.kill_switch.is_set():
                cleanup = self._terminate(child)
                return self._result(command_value, child.returncode, stdout_b, stderr_b, started, policy, cancelled=True, cleanup=cleanup, on_output=on_output)
            return self._result(command_value, child.returncode, stdout_b, stderr_b, started, policy, cleanup=cleanup, on_output=on_output)
        finally:
            if child is not None:
                with self._lock:
                    self._children.discard(child)

    @staticmethod
    def _decode_bounded(value: bytes | str | None, limit: int) -> tuple[str, bool]:
        raw = value.encode("utf-8", errors="replace") if isinstance(value, str) else (value or b"")
        truncated = len(raw) > limit
        if truncated:
            raw = raw[:limit]
        return raw.decode("utf-8", errors="replace"), truncated

    def _result(self, command, returncode, stdout, stderr, started, limits, *, timed_out=False, cancelled=False, cleanup="not_required", on_output=None) -> ProcessResult:
        out, out_cut = self._decode_bounded(stdout, limits.max_output_bytes)
        err, err_cut = self._decode_bounded(stderr, limits.max_output_bytes)
        if on_output:
            on_output(out, err)
        return ProcessResult(
            command=command,
            returncode=returncode,
            stdout=out,
            stderr=err,
            duration_seconds=max(0.0, time.monotonic() - started),
            timed_out=timed_out,
            cancelled=cancelled,
            output_truncated=out_cut or err_cut,
            orphan_cleanup=cleanup,
        )

    def _terminate(self, child: subprocess.Popen) -> str:
        if child.poll() is not None:
            return "already_exited"
        try:
            if os.name == "nt":
                child.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                self._signal_process_group(child, "SIGTERM")
            child.wait(timeout=2.0)
            return "process_group_terminated"
        except Exception:
            try:
                if os.name == "nt":
                    child.kill()
                else:
                    self._signal_process_group(child, "SIGKILL")
                child.wait(timeout=2.0)
                return "process_group_killed"
            except Exception as exc:  # pragma: no cover - platform-specific failure
                return f"cleanup_incomplete:{type(exc).__name__}"

    @staticmethod
    def _signal_process_group(child: subprocess.Popen, signal_name: str) -> None:
        killpg = getattr(os, "killpg", None)
        getpgid = getattr(os, "getpgid", None)
        sig = getattr(signal, signal_name, None)
        if not callable(killpg) or not callable(getpgid) or sig is None:
            child.kill()
            return
        killpg(getpgid(child.pid), sig)
