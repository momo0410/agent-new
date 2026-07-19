"""Run the repository-visible correctness, reliability and safety benchmark."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.benchmark_worker import SubprocessBenchmarkExecutor
from app.core.evaluation import BenchmarkExecutionCase, BenchmarkGate, BenchmarkManifest, BenchmarkRunner


class PublicFixtureExecutor:
    """Deterministic CI fixture adapter; truth remains in the manifest runner."""

    def __init__(self, fixture_path: Path):
        raw = json.loads(fixture_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not raw:
            raise ValueError("public benchmark fixture mapping is empty")
        self.fixtures = raw

    def __call__(self, case: BenchmarkExecutionCase) -> dict[str, Any]:
        fixture = self.fixtures.get(case.fixture_ref)
        if not isinstance(fixture, dict):
            return {"status": "FAILED", "error": "fixture reference is missing"}
        # The evaluated adapter receives no case ID and no expected status.
        return {
            "status": str(fixture.get("status", "INCONCLUSIVE")),
            "cost": float(fixture.get("cost", 0.0) or 0.0),
            "repeated_actions": int(fixture.get("repeated_actions", 0) or 0),
            "security_events": int(fixture.get("security_events", 0) or 0),
        }


def _mapping(name: str) -> dict[str, float] | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError(f"{name} must be a JSON object")
    return {str(key): float(item) for key, item in parsed.items()}


def main() -> int:
    manifest_path = Path(os.environ.get("SDIT_PUBLIC_BENCHMARK_MANIFEST", ROOT / "benchmarks" / "public-manifest.v1.json"))
    fixture_path = Path(os.environ.get("SDIT_PUBLIC_BENCHMARK_FIXTURES", ROOT / "benchmarks" / "public-fixtures.v1.json"))
    output_path = Path(os.environ.get("SDIT_PUBLIC_BENCHMARK_REPORT", ROOT / "public-benchmark-report.json"))
    repetitions = int(os.environ.get("SDIT_BENCHMARK_REPETITIONS", "3"))
    external_runner = os.environ.get("SDIT_PUBLIC_BENCHMARK_CASE_RUNNER", "").strip()
    executor = (
        SubprocessBenchmarkExecutor(
            external_runner,
            timeout_seconds=float(os.environ.get("SDIT_BENCHMARK_CASE_TIMEOUT", "300")),
        )
        if external_runner
        else PublicFixtureExecutor(fixture_path)
    )
    manifest = BenchmarkManifest.from_json(manifest_path)
    report = BenchmarkRunner(executor).run(manifest, repetitions=repetitions)
    gate = BenchmarkGate(
        thresholds=_mapping("SDIT_BENCHMARK_MINIMUMS"),
        maximums=_mapping("SDIT_BENCHMARK_MAXIMUMS"),
    )
    passed, failures = gate.check(report)
    payload = report.as_dict()
    payload["passed"] = passed
    payload["failures"] = failures
    payload["report_digest"] = __import__("hashlib").sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(output_path)
    print(json.dumps({
        "report": str(output_path),
        "manifest_version": report.manifest_version,
        "repetitions": report.repetitions,
        "metrics": report.metrics(),
        "passed": passed,
        "failures": failures,
    }, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
