from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys

import pytest

from app.core.benchmark_worker import HiddenBenchmarkWorker, SubprocessBenchmarkExecutor
from app.core.evaluation import BenchmarkGate, BenchmarkRunner, HiddenBenchmarkProvider, ModelReplacementGate


def _signed_manifest():
    key = "fixture-key"
    payload = json.dumps(
        {
            "version": "hidden-v1",
            "cases": [
                {
                    "case_id": "case-secret",
                    "category": "modern_web",
                    "expected_status": "INCONCLUSIVE",
                    "target_ref": "fixture-ref",
                }
            ],
        },
        separators=(",", ":"),
    ).encode()
    encoded = base64.b64encode(payload).decode()
    signature = hmac.new(key.encode(), payload, hashlib.sha256).hexdigest()
    return encoded, signature, key


def test_hidden_manifest_requires_signature_and_is_redacted():
    encoded, signature, key = _signed_manifest()
    manifest = HiddenBenchmarkProvider.load_signed(encoded, signature, key)
    assert manifest.cases[0].hidden
    with pytest.raises(ValueError):
        HiddenBenchmarkProvider.load_signed(encoded, "wrong", key)


def test_hidden_runner_requires_repeated_measurements_and_gate_stays_strict():
    encoded, signature, key = _signed_manifest()
    manifest = HiddenBenchmarkProvider.load_signed(encoded, signature, key)
    observed_inputs = []

    def execute(case):
        observed_inputs.append(case)
        return {"status": "INCONCLUSIVE"}

    runner = BenchmarkRunner(execute)
    with pytest.raises(ValueError):
        runner.run(manifest, repetitions=1)
    report = runner.run(manifest, repetitions=3)
    assert report.metrics()["flaky_case_rate"] == 0
    serialized = report.as_dict()
    assert serialized["cases"][0]["expected_status"] == "REDACTED"
    assert not hasattr(observed_inputs[0], "expected_status")
    assert observed_inputs[0].category == "hidden"
    assert not BenchmarkGate(thresholds={"VPR": 1.1}).check(report)[0]


def test_hidden_worker_removes_truth_and_secret_environment(monkeypatch, tmp_path):
    encoded, signature, key = _signed_manifest()
    runner = tmp_path / "case_runner.py"
    runner.write_text(
        """
import json
import os
import sys

case = json.loads(sys.stdin.read())
assert "expected_status" not in case
assert "case_id" not in case
assert "SDIT_HIDDEN_BENCHMARK_KEY" not in os.environ
print(json.dumps({"status": "INCONCLUSIVE", "cost": 0.01}))
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("SDIT_HIDDEN_BENCHMARK_B64", encoded)
    monkeypatch.setenv("SDIT_HIDDEN_BENCHMARK_SIGNATURE", signature)
    monkeypatch.setenv("SDIT_HIDDEN_BENCHMARK_KEY", key)
    worker = HiddenBenchmarkWorker(SubprocessBenchmarkExecutor([sys.executable, str(runner)]))
    report, failures = worker.run_from_environment()
    assert not failures
    assert report.repetitions == 3
    assert "SDIT_HIDDEN_BENCHMARK_KEY" not in __import__("os").environ
    payload = worker.write_redacted(report, tmp_path / "report.json")
    assert payload["report_digest"]
    assert "fixture-ref" not in (tmp_path / "report.json").read_text(encoding="utf-8")


def test_model_replacement_gate_compares_same_version_metrics():
    baseline = {
        "manifest_version": "v1",
        "repetitions": 3,
        "cases": [{"case_id": "redacted"}],
        "metrics": {"VPR": 1.0, "verified_recall": 1.0, "session_accuracy": 1.0,
                     "false_positive_rate": 0.0, "security_events": 0, "flaky_case_rate": 0.0, "total_cost": 10},
    }
    candidate = dict(baseline, metrics={**baseline["metrics"], "total_cost": 10.1})
    assert ModelReplacementGate().check(baseline, candidate)[0]
    candidate["metrics"] = {**candidate["metrics"], "VPR": 0.8}
    assert not ModelReplacementGate().check(baseline, candidate)[0]
