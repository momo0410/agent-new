from __future__ import annotations

import json
from pathlib import Path

from app.core.evaluation import BenchmarkManifest, BenchmarkRunner
from scripts.run_public_benchmark import PublicFixtureExecutor


ROOT = Path(__file__).resolve().parents[1]


def test_public_benchmark_covers_required_categories_and_three_repetitions():
    manifest = BenchmarkManifest.from_json(ROOT / "benchmarks" / "public-manifest.v1.json")
    categories = {case.category for case in manifest.cases}
    assert {
        "known_linux",
        "unknown_linux",
        "misconfiguration",
        "modern_web",
        "negative",
        "unstable_network",
    }.issubset(categories)
    report = BenchmarkRunner(
        PublicFixtureExecutor(ROOT / "benchmarks" / "public-fixtures.v1.json")
    ).run(manifest, repetitions=3)
    assert report.repetitions == 3
    assert len(report.cases) == len(manifest.cases) * 3
    assert report.metrics()["flaky_case_rate"] == 0.0
    assert report.metrics()["VPR"] == 1.0


def test_public_fixture_adapter_receives_truth_free_execution_case():
    raw = json.loads((ROOT / "benchmarks" / "public-manifest.v1.json").read_text(encoding="utf-8"))
    assert all("expected_status" in item for item in raw["cases"])
    # The core BenchmarkExecutionCase contract intentionally has no expected_status field.
    from app.core.evaluation import BenchmarkExecutionCase

    assert "expected_status" not in BenchmarkExecutionCase.__dataclass_fields__
    assert "case_id" not in BenchmarkExecutionCase.__dataclass_fields__
