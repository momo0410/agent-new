from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DoneGateResult:
    can_close: bool
    reasons: tuple[str, ...] = ()
    unresolved: tuple[dict[str, Any], ...] = ()
    terminal_count: int = 0
    checks: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "can_close": self.can_close,
            "reasons": list(self.reasons),
            "unresolved": list(self.unresolved),
            "terminal_count": self.terminal_count,
            "checks": list(self.checks),
        }


class DoneGate:
    TERMINAL = {
        "verified", "exploited", "evidence_complete", "exhausted",
        "not_applicable", "blocked", "out_of_scope", "blocked_by_policy",
        "unreachable", "vulnerability_confirmed", "objective_completed",
        "failed", "inconclusive", "cancelled",
    }

    def __init__(self, *, must_try_score: int = 50):
        self.must_try_score = must_try_score

    def evaluate(
        self,
        surfaces: list[dict[str, Any]],
        *,
        budget_exhausted: bool = False,
        report_complete: bool = False,
        task_cancelled: bool = False,
        targets: list[dict[str, Any]] | None = None,
        unresolved_evidence: list[dict[str, Any]] | None = None,
        sessions: list[dict[str, Any]] | None = None,
        objective_required: bool = False,
        objective_completed: bool = False,
    ) -> DoneGateResult:
        unresolved: list[dict[str, Any]] = []
        terminal_count = 0
        for surface in surfaces:
            if not isinstance(surface, dict):
                continue
            score = int(surface.get("score", surface.get("priority", 0)) or 0)
            status = str(surface.get("status", "unobserved")).strip().lower()
            if score < self.must_try_score:
                continue
            if status in self.TERMINAL:
                terminal_count += 1
                continue
            unresolved.append({
                "surface_id": str(surface.get("surface_id", surface.get("id", ""))),
                "score": score,
                "status": status,
                "reason": str(surface.get("reason", "high-value surface has no terminal conclusion")),
            })
        reasons: list[str] = []
        checks: list[dict[str, Any]] = []
        if unresolved and not (budget_exhausted or task_cancelled):
            reasons.append("high-value attack surfaces remain unresolved")
        checks.append({"name": "must_try", "passed": not unresolved, "count": len(unresolved)})
        if unresolved and budget_exhausted:
            for item in unresolved:
                if not item.get("surface_id"):
                    reasons.append("budget exhaustion requires identifiable surface evidence")
        if not report_complete and not task_cancelled:
            reasons.append("report completeness has not been verified")
        checks.append({"name": "report", "passed": bool(report_complete or task_cancelled)})
        checks.append({
            "name": "budget",
            "passed": True,
            "exhausted": bool(budget_exhausted),
            "closure_basis": "budget_exhausted" if budget_exhausted else "within_budget",
        })
        target_items = [item for item in (targets or []) if isinstance(item, dict)]
        uncovered_targets = [
            item for item in target_items
            if str(item.get("status", "")).lower() not in self.TERMINAL
        ]
        if uncovered_targets and not (budget_exhausted or task_cancelled):
            reasons.append("target coverage is incomplete")
        checks.append({"name": "target_coverage", "passed": not uncovered_targets, "count": len(uncovered_targets)})
        evidence_items = [item for item in (unresolved_evidence or []) if isinstance(item, dict)]
        if evidence_items and not (budget_exhausted or task_cancelled):
            reasons.append("evidence conclusions remain unresolved")
        checks.append({"name": "evidence", "passed": not evidence_items, "count": len(evidence_items)})
        live_sessions = [
            item for item in (sessions or []) if isinstance(item, dict)
            and str(item.get("status", "")).lower() in {"connected", "active", "open"}
            and not item.get("cleanup_complete", False)
        ]
        if live_sessions and not task_cancelled:
            reasons.append("active sessions require closure or explicit retention")
        checks.append({"name": "sessions", "passed": not live_sessions, "count": len(live_sessions)})
        if objective_required and not objective_completed and not (budget_exhausted or task_cancelled):
            reasons.append("task objective is incomplete")
        checks.append({"name": "objective", "passed": bool(not objective_required or objective_completed or budget_exhausted or task_cancelled)})
        return DoneGateResult(
            can_close=not reasons,
            reasons=tuple(dict.fromkeys(reasons)),
            unresolved=tuple(unresolved),
            terminal_count=terminal_count,
            checks=tuple(checks),
        )
