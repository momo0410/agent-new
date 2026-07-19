"""Isolated benchmark worker that never passes expected truth to case runners."""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .evaluation import (
    BenchmarkExecutionCase,
    BenchmarkGate,
    BenchmarkReport,
    BenchmarkRunner,
    HiddenBenchmarkProvider,
)

_HIDDEN_ENV_KEYS = (
    "SDIT_HIDDEN_BENCHMARK_B64",
    "SDIT_HIDDEN_BENCHMARK_SIGNATURE",
    "SDIT_HIDDEN_BENCHMARK_KEY",
)


class BenchmarkWorkerError(RuntimeError):
    pass


class SubprocessBenchmarkExecutor:
    """Invoke a case runner in a child process with a truth-free JSON request."""

    def __init__(self, command: str | list[str], *, timeout_seconds: float = 300.0) -> None:
        if isinstance(command, str):
            argv = shlex.split(command, posix=os.name != "nt")
        else:
            argv = [str(item) for item in command]
        if not argv:
            raise BenchmarkWorkerError("benchmark case runner command is required")
        self.argv = argv
        self.timeout_seconds = max(1.0, float(timeout_seconds))

    def __call__(self, case: BenchmarkExecutionCase) -> dict[str, Any]:
        child_env = dict(os.environ)
        for key in _HIDDEN_ENV_KEYS:
            child_env.pop(key, None)
        child_env.pop("SDIT_HIDDEN_BENCHMARK_CONTEXT", None)
        request = json.dumps(asdict(case), ensure_ascii=False, separators=(",", ":"))
        completed = subprocess.run(  # noqa: S603 - argv is an explicit protected-runner contract
            self.argv,
            input=request,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
            env=child_env,
            shell=False,
        )
        if completed.returncode != 0:
            raise BenchmarkWorkerError(
                f"case runner exited with code {completed.returncode}: {completed.stderr[-500:]}"
            )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if not lines:
            raise BenchmarkWorkerError("case runner returned no result")
        try:
            result = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            raise BenchmarkWorkerError("case runner result is not JSON") from exc
        if not isinstance(result, dict) or not str(result.get("status", "")).strip():
            raise BenchmarkWorkerError("case runner result has no status")
        return result


class HiddenBenchmarkWorker:
    def __init__(
        self,
        executor: SubprocessBenchmarkExecutor,
        *,
        gate: BenchmarkGate | None = None,
        repetitions: int = 3,
    ) -> None:
        self.executor = executor
        self.gate = gate or BenchmarkGate()
        self.repetitions = max(3, int(repetitions))

    def run_from_environment(self) -> tuple[BenchmarkReport, list[str]]:
        os.environ["SDIT_EVALUATION_WORKER"] = "1"
        manifest = HiddenBenchmarkProvider.from_environment()
        for key in _HIDDEN_ENV_KEYS:
            os.environ.pop(key, None)
        report = BenchmarkRunner(self.executor).run(manifest, repetitions=self.repetitions)
        passed, failures = self.gate.check(report)
        if not passed:
            return report, failures
        return report, []

    @staticmethod
    def write_redacted(report: BenchmarkReport, output: str | Path) -> dict[str, Any]:
        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = report.as_dict()
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload["report_digest"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload


__all__ = ["BenchmarkWorkerError", "SubprocessBenchmarkExecutor", "HiddenBenchmarkWorker"]
