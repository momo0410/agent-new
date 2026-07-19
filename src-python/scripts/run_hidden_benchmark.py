"""Protected CI entrypoint for the signed hidden benchmark suite."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.benchmark_worker import HiddenBenchmarkWorker, SubprocessBenchmarkExecutor
from app.core.evaluation import BenchmarkGate


def _json_mapping(name: str) -> dict[str, float]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return {str(key): float(item) for key, item in value.items()}


def main() -> int:
    command = os.environ.get("SDIT_BENCHMARK_CASE_RUNNER", "").strip()
    output = Path(os.environ.get("SDIT_HIDDEN_BENCHMARK_REPORT", "hidden-benchmark-report.json"))
    repetitions = int(os.environ.get("SDIT_BENCHMARK_REPETITIONS", "3"))
    timeout_seconds = float(os.environ.get("SDIT_BENCHMARK_CASE_TIMEOUT", "300"))
    thresholds = _json_mapping("SDIT_BENCHMARK_MINIMUMS") or None
    maximums = _json_mapping("SDIT_BENCHMARK_MAXIMUMS") or None
    worker = HiddenBenchmarkWorker(
        SubprocessBenchmarkExecutor(command, timeout_seconds=timeout_seconds),
        gate=BenchmarkGate(thresholds=thresholds, maximums=maximums),
        repetitions=repetitions,
    )
    report, failures = worker.run_from_environment()
    payload = worker.write_redacted(report, output)
    print(json.dumps({
        "report": str(output),
        "manifest_version": payload["manifest_version"],
        "repetitions": payload["repetitions"],
        "metrics": payload["metrics"],
        "report_digest": payload["report_digest"],
        "passed": not failures,
        "failures": failures,
    }, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
