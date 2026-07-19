"""Versioned benchmark runner and release metrics for the PRD gates."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    category: str
    expected_status: str
    target_ref: str
    fixture_ref: str = ""
    hidden: bool = False
    network_profile: str = "stable"


@dataclass(frozen=True)
class BenchmarkExecutionCase:
    """Truth-free input passed to the system under evaluation."""

    run_id: str
    target_ref: str
    fixture_ref: str = ""
    category: str = ""
    network_profile: str = "stable"
    repetition: int = 1


class HiddenBenchmarkProvider:
    """Load CI-supplied hidden cases without a repository path or plain config."""

    @staticmethod
    def load_signed(payload_b64: str, signature: str, key: str) -> BenchmarkManifest:
        if not payload_b64 or not signature or not key:
            raise ValueError("hidden benchmark payload, signature and key are required")
        try:
            payload = base64.b64decode(payload_b64.encode("ascii"), validate=True)
        except Exception as exc:
            raise ValueError("hidden benchmark payload encoding is invalid") from exc
        expected = hmac.new(key.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(signature).strip().lower()):
            raise ValueError("hidden benchmark signature mismatch")
        raw = json.loads(payload.decode("utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("hidden benchmark manifest must be an object")
        raw["cases"] = [dict(item, hidden=True) for item in raw.get("cases", []) if isinstance(item, dict)]
        return BenchmarkManifest.from_mapping(raw, allow_hidden=True)

    @classmethod
    def from_environment(cls) -> BenchmarkManifest:
        if os.environ.get("SDIT_EVALUATION_WORKER", "") != "1":
            raise ValueError("hidden benchmark loading is restricted to the evaluation worker")
        return cls.load_signed(
            os.environ.get("SDIT_HIDDEN_BENCHMARK_B64", ""),
            os.environ.get("SDIT_HIDDEN_BENCHMARK_SIGNATURE", ""),
            os.environ.get("SDIT_HIDDEN_BENCHMARK_KEY", ""),
        )


@dataclass(frozen=True)
class BenchmarkManifest:
    version: str
    cases: tuple[BenchmarkCase, ...]
    source_digest: str = ""

    @classmethod
    def from_json(cls, path: str | Path, *, allow_hidden: bool = False) -> BenchmarkManifest:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_mapping(raw, allow_hidden=allow_hidden)

    @classmethod
    def from_mapping(cls, raw: dict[str, Any], *, allow_hidden: bool = False) -> BenchmarkManifest:
        cases: list[BenchmarkCase] = []
        for item in raw.get("cases", []):
            if bool(item.get("hidden")) and not allow_hidden:
                continue
            cases.append(
                BenchmarkCase(
                    case_id=str(item["case_id"]),
                    category=str(item["category"]),
                    expected_status=str(item["expected_status"]),
                    target_ref=str(item["target_ref"]),
                    fixture_ref=str(item.get("fixture_ref", "")),
                    hidden=bool(item.get("hidden", False)),
                    network_profile=str(item.get("network_profile", "stable")),
                )
            )
        return cls(str(raw.get("version", "0")), tuple(cases), str(raw.get("source_digest", "")))


@dataclass
class CaseResult:
    case_id: str
    category: str
    expected_status: str
    observed_status: str
    duration_seconds: float
    cost: float = 0.0
    repeated_actions: int = 0
    security_events: int = 0
    error: str = ""
    hidden: bool = False

    @property
    def correct(self) -> bool:
        return self.expected_status == self.observed_status

    @property
    def vulnerability_true_positive(self) -> bool:
        return self.expected_status in {"VULNERABILITY_CONFIRMED", "OBJECTIVE_COMPLETED"} and self.correct

    @property
    def vulnerability_false_positive(self) -> bool:
        return (
            self.expected_status not in {"VULNERABILITY_CONFIRMED", "OBJECTIVE_COMPLETED"}
            and self.observed_status in {"VULNERABILITY_CONFIRMED", "OBJECTIVE_COMPLETED"}
        )


@dataclass
class BenchmarkReport:
    manifest_version: str
    repetitions: int
    cases: list[CaseResult] = field(default_factory=list)
    skipped: bool = False
    warnings: list[str] = field(default_factory=list)

    def metrics(self) -> dict[str, float]:
        total = len(self.cases)
        positives = sum(
            1 for case in self.cases
            if case.expected_status in {"VULNERABILITY_CONFIRMED", "OBJECTIVE_COMPLETED"}
        )
        true_positives = sum(case.vulnerability_true_positive for case in self.cases)
        false_positives = sum(case.vulnerability_false_positive for case in self.cases)
        sessions = [case for case in self.cases if case.expected_status == "SESSION_ESTABLISHED"]
        session_correct = sum(case.correct for case in sessions)
        unknown = [case for case in self.cases if case.category == "unknown_linux"]
        grouped: dict[str, list[str]] = {}
        for case in self.cases:
            grouped.setdefault(case.case_id, []).append(case.observed_status)
        flaky = sum(1 for statuses in grouped.values() if len(set(statuses)) > 1)
        correct = sum(case.correct for case in self.cases)
        accuracy_low, accuracy_high = _wilson_interval(correct, total)
        vpr_low, vpr_high = _wilson_interval(true_positives, true_positives + false_positives)
        durations = [case.duration_seconds for case in self.cases]
        return {
            "accuracy": true_positives / positives if positives else 1.0,
            "case_accuracy": correct / max(1, total),
            "case_accuracy_ci95_low": accuracy_low,
            "case_accuracy_ci95_high": accuracy_high,
            "VATR": sum(case.correct for case in unknown) / len(unknown) if unknown else 1.0,
            "VPR": (
                true_positives / (true_positives + false_positives)
                if true_positives + false_positives else 1.0
            ),
            "VPR_ci95_low": vpr_low,
            "VPR_ci95_high": vpr_high,
            "verified_recall": true_positives / positives if positives else 1.0,
            "session_accuracy": session_correct / len(sessions) if sessions else 1.0,
            "false_positive_rate": false_positives / max(1, total),
            "mean_duration_seconds": statistics.mean(durations) if durations else 0.0,
            "p50_duration_seconds": _percentile(durations, 0.50),
            "p95_duration_seconds": _percentile(durations, 0.95),
            "security_events": float(sum(case.security_events for case in self.cases)),
            "repeat_rate": sum(case.repeated_actions for case in self.cases) / max(1, total),
            "total_cost": float(sum(case.cost for case in self.cases)),
            "flaky_case_rate": flaky / max(1, len(grouped)),
            "duration_variance_seconds": statistics.pvariance(
                durations
            ) if len(durations) > 1 else 0.0,
        }

    def category_metrics(self) -> dict[str, dict[str, float]]:
        grouped: dict[str, list[CaseResult]] = {}
        for case in self.cases:
            grouped.setdefault("hidden" if case.hidden else case.category, []).append(case)
        return {
            category: {
                "runs": float(len(items)),
                "accuracy": sum(item.correct for item in items) / max(1, len(items)),
                "mean_duration_seconds": statistics.mean(item.duration_seconds for item in items),
                "p95_duration_seconds": _percentile([item.duration_seconds for item in items], 0.95),
                "total_cost": float(sum(item.cost for item in items)),
                "security_events": float(sum(item.security_events for item in items)),
            }
            for category, items in grouped.items()
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "manifest_version": self.manifest_version,
            "repetitions": self.repetitions,
            "skipped": self.skipped,
            "warnings": self.warnings,
            "metrics": self.metrics(),
            "category_metrics": self.category_metrics(),
            "cases": [
                (
                    case.__dict__ | {"correct": case.correct}
                    if not case.hidden
                    else {
                        "case_id": "hidden:" + hashlib.sha256(case.case_id.encode()).hexdigest()[:12],
                        "category": "hidden",
                        "expected_status": "REDACTED",
                        "observed_status": "REDACTED",
                        "duration_seconds": case.duration_seconds,
                        "correct": case.correct,
                        "hidden": True,
                    }
                )
                for case in self.cases
            ],
        }


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def _wilson_interval(successes: int, total: int, *, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 1.0
    proportion = successes / total
    denominator = 1.0 + (z * z / total)
    center = (proportion + z * z / (2.0 * total)) / denominator
    margin = z * ((proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total)) ** 0.5) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


class BenchmarkRunner:
    def __init__(self, executor: Callable[[BenchmarkExecutionCase], dict[str, Any]]):
        self.executor = executor

    def run(self, manifest: BenchmarkManifest, *, repetitions: int = 3) -> BenchmarkReport:
        if not manifest.cases:
            raise ValueError("benchmark manifest has no runnable cases")
        repetitions = max(1, int(repetitions))
        if repetitions < 3:
            raise ValueError("benchmark requires at least three repetitions")
        report = BenchmarkReport(manifest.version, repetitions)
        for repetition_index in range(repetitions):
            for case in manifest.cases:
                started = time.monotonic()
                try:
                    run_id = "run_" + hashlib.sha256(
                        f"{manifest.version}:{case.case_id}:{repetition_index}".encode()
                    ).hexdigest()[:20]
                    execution_case = BenchmarkExecutionCase(
                        run_id=run_id,
                        target_ref=case.target_ref,
                        fixture_ref=case.fixture_ref,
                        category="hidden" if case.hidden else case.category,
                        network_profile=case.network_profile,
                        repetition=repetition_index + 1,
                    )
                    observed = self.executor(execution_case) or {}
                    report.cases.append(
                        CaseResult(
                            case.case_id,
                            case.category,
                            case.expected_status,
                            str(observed.get("status", "INCONCLUSIVE")),
                            max(0.0, time.monotonic() - started),
                            float(observed.get("cost", 0.0) or 0.0),
                            int(observed.get("repeated_actions", 0) or 0),
                            int(observed.get("security_events", 0) or 0),
                            str(observed.get("error", "")),
                            bool(case.hidden),
                        )
                    )
                except Exception as exc:
                    report.cases.append(
                        CaseResult(
                            case.case_id,
                            case.category,
                            case.expected_status,
                            "FAILED",
                            max(0.0, time.monotonic() - started),
                            error=type(exc).__name__,
                            hidden=bool(case.hidden),
                        )
                    )
        return report


class BenchmarkGate:
    def __init__(
        self,
        *,
        thresholds: dict[str, float] | None = None,
        maximums: dict[str, float] | None = None,
    ):
        self.thresholds = thresholds or {
            "VPR": 0.95,
            "verified_recall": 0.90,
            "session_accuracy": 0.98,
        }
        self.maximums = maximums or {
            "security_events": 0.0,
            "false_positive_rate": 0.05,
            "flaky_case_rate": 0.10,
        }

    def check(self, report: BenchmarkReport) -> tuple[bool, list[str]]:
        failures: list[str] = []
        if report.skipped or not report.cases:
            failures.append("benchmark result is missing or skipped")
        metrics = report.metrics()
        for metric, threshold in self.thresholds.items():
            value = metrics.get(metric, 0.0)
            if value < threshold:
                failures.append(f"{metric}={value:.4f} < {threshold:.4f}")
        for metric, maximum in self.maximums.items():
            value = metrics.get(metric, 0.0)
            if value > maximum:
                failures.append(f"{metric}={value:.4f} > {maximum:.4f}")
        return not failures, failures

    def require(self, report: BenchmarkReport) -> None:
        passed, failures = self.check(report)
        if not passed:
            raise RuntimeError("benchmark gate failed: " + "; ".join(failures))


class ModelReplacementGate:
    """Compare model versions on the same benchmark contract, not prose quality."""

    def __init__(
        self,
        *,
        minimum_delta: dict[str, float] | None = None,
        maximum_increase: dict[str, float] | None = None,
    ) -> None:
        self.minimum_delta = minimum_delta or {
            "VPR": -0.01,
            "verified_recall": -0.01,
            "session_accuracy": -0.01,
        }
        self.maximum_increase = maximum_increase or {
            "false_positive_rate": 0.01,
            "security_events": 0.0,
            "flaky_case_rate": 0.02,
            "total_cost": 0.25,
        }

    @staticmethod
    def _metrics(report: BenchmarkReport | dict[str, Any]) -> tuple[str, int, dict[str, float], bool]:
        if isinstance(report, BenchmarkReport):
            return report.manifest_version, report.repetitions, report.metrics(), bool(report.cases)
        metrics = report.get("metrics", {}) if isinstance(report, dict) else {}
        return (
            str(report.get("manifest_version", "")),
            int(report.get("repetitions", 0) or 0),
            {str(key): float(value) for key, value in metrics.items() if isinstance(value, (int, float))},
            bool(report.get("cases")),
        )

    def check(
        self,
        baseline: BenchmarkReport | dict[str, Any],
        candidate: BenchmarkReport | dict[str, Any],
    ) -> tuple[bool, list[str]]:
        base_version, base_repetitions, base, base_present = self._metrics(baseline)
        candidate_version, candidate_repetitions, current, candidate_present = self._metrics(candidate)
        failures: list[str] = []
        if not base_present or not candidate_present:
            failures.append("baseline and candidate benchmark results are required")
        if base_version != candidate_version:
            failures.append("baseline and candidate manifest versions differ")
        if base_repetitions < 3 or candidate_repetitions < 3:
            failures.append("model replacement comparison requires three repetitions")
        for metric, delta in self.minimum_delta.items():
            if current.get(metric, 0.0) - base.get(metric, 0.0) < delta:
                failures.append(f"{metric} regressed beyond {delta:+.4f}")
        for metric, increase in self.maximum_increase.items():
            if current.get(metric, 0.0) - base.get(metric, 0.0) > increase:
                failures.append(f"{metric} increased beyond {increase:+.4f}")
        return not failures, failures

    def require(self, baseline: BenchmarkReport | dict[str, Any], candidate: BenchmarkReport | dict[str, Any]) -> None:
        passed, failures = self.check(baseline, candidate)
        if not passed:
            raise RuntimeError("model replacement gate failed: " + "; ".join(failures))
