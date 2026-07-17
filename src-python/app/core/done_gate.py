from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DoneGateResult:
    can_close: bool
    reasons: tuple[str, ...] = ()
    unresolved: tuple[dict[str, Any], ...] = ()
    terminal_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "can_close": self.can_close,
            "reasons": list(self.reasons),
            "unresolved": list(self.unresolved),
            "terminal_count": self.terminal_count,
        }


class DoneGate:
    TERMINAL = {"verified", "exploited", "evidence_complete", "exhausted", "not_applicable", "blocked"}

    def __init__(self, *, must_try_score: int = 50):
        self.must_try_score = must_try_score

    def evaluate(
        self,
        surfaces: list[dict[str, Any]],
        *,
        budget_exhausted: bool = False,
        report_complete: bool = False,
        task_cancelled: bool = False,
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
        if unresolved and not (budget_exhausted or task_cancelled):
            reasons.append("high-value attack surfaces remain unresolved")
        if unresolved and budget_exhausted:
            for item in unresolved:
                if not item.get("surface_id"):
                    reasons.append("budget exhaustion requires identifiable surface evidence")
        if not report_complete and not task_cancelled:
            reasons.append("report completeness has not been verified")
        return DoneGateResult(
            can_close=not reasons,
            reasons=tuple(dict.fromkeys(reasons)),
            unresolved=tuple(unresolved),
            terminal_count=terminal_count,
        )

