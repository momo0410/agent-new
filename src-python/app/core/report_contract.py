"""Report snapshot contracts and completeness validation."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

REQUIRED_REPORT_SECTIONS = (
    "management_summary",
    "technical_findings",
    "attack_path",
    "evidence",
    "failure_path",
    "coverage",
    "limitations",
    "remediation",
)

REQUIRED_HIGH_RISK_FIELDS = (
    "why_suspected",
    "verification_method",
    "proof_evidence",
    "impact",
    "reproduction",
    "remediation",
)


@dataclass(frozen=True)
class ReportSnapshot:
    task_id: str
    task_version: str
    template_version: str
    generated_at: datetime
    sections: dict[str, Any]
    evidence_manifest: tuple[dict[str, Any], ...] = ()
    integrity_hash: str = ""

    @classmethod
    def from_document(
        cls,
        document: dict[str, Any],
        *,
        task_version: str = "state.v1",
        template_version: str = "report-document.v1",
    ) -> ReportSnapshot:
        """Create a validator snapshot from the canonical multi-format document."""
        generated = document.get("generated_at")
        try:
            generated_at = datetime.fromisoformat(str(generated))
        except (TypeError, ValueError):
            generated_at = datetime.now().astimezone()
        evidence = document.get("evidence", [])
        manifest = tuple(item for item in evidence if isinstance(item, dict)) if isinstance(evidence, list) else ()
        snapshot = cls(
            task_id=str(document.get("task_id", "")),
            task_version=str(task_version),
            template_version=str(document.get("schema_version") or template_version),
            generated_at=generated_at,
            sections={section: document.get(section) for section in REQUIRED_REPORT_SECTIONS if section in document},
            evidence_manifest=manifest,
        )
        return snapshot.with_integrity()

    def with_integrity(self) -> ReportSnapshot:
        payload = {
            "task_id": self.task_id,
            "task_version": self.task_version,
            "template_version": self.template_version,
            "generated_at": self.generated_at.isoformat(),
            "sections": self.sections,
            "evidence_manifest": list(self.evidence_manifest),
        }
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
        return ReportSnapshot(**{**self.__dict__, "integrity_hash": digest})


@dataclass(frozen=True)
class ReportCheck:
    complete: bool
    missing_sections: tuple[str, ...] = ()
    unreferenced_findings: tuple[str, ...] = ()
    integrity_valid: bool = True
    reasons: tuple[str, ...] = ()
    incomplete_high_risk_findings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "complete": self.complete,
            "missing_sections": list(self.missing_sections),
            "unreferenced_findings": list(self.unreferenced_findings),
            "integrity_valid": self.integrity_valid,
            "reasons": list(self.reasons),
            "incomplete_high_risk_findings": list(self.incomplete_high_risk_findings),
        }


class ReportCompletenessValidator:
    def validate(self, report: ReportSnapshot, *, finding_ids: set[str] | None = None) -> ReportCheck:
        missing = tuple(section for section in REQUIRED_REPORT_SECTIONS if section not in report.sections)
        refs: set[str] = set()
        for item in report.evidence_manifest:
            if isinstance(item, dict):
                refs.update(str(value) for value in item.get("finding_ids", []) or [])
                if item.get("finding_id"):
                    refs.add(str(item["finding_id"]))
        unreferenced = tuple(sorted((finding_ids or set()) - refs))
        reasons: list[str] = []
        if missing:
            reasons.append("required report sections are missing")
        if unreferenced:
            reasons.append("findings are not traceable to evidence")
        incomplete_high_risk = self._incomplete_high_risk_findings(report.sections.get("technical_findings"))
        if incomplete_high_risk:
            reasons.append("high-risk findings have incomplete proof or remediation fields")
        valid_integrity = self._integrity_valid(report)
        if not valid_integrity:
            reasons.append("report integrity hash mismatch")
        return ReportCheck(
            complete=not missing and not unreferenced and not incomplete_high_risk and valid_integrity,
            missing_sections=missing,
            unreferenced_findings=unreferenced,
            integrity_valid=valid_integrity,
            reasons=tuple(reasons),
            incomplete_high_risk_findings=incomplete_high_risk,
        )

    @staticmethod
    def _incomplete_high_risk_findings(value: Any) -> tuple[str, ...]:
        if not isinstance(value, list):
            return ()
        incomplete: list[str] = []
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                continue
            severity = str(item.get("severity", "")).strip().lower()
            status = str(item.get("status", "")).strip().lower().replace(" ", "_")
            risk_class = str(item.get("risk_class", "")).strip().lower()
            try:
                score = float(item.get("score", item.get("cvss_score", 0)) or 0)
            except (TypeError, ValueError):
                score = 0.0
            high_risk = (
                risk_class == "high"
                or severity in {"high", "critical", "严重", "高危"}
                or status in {
                    "confirmed", "vulnerable", "exploited", "vulnerability_confirmed",
                    "verified", "identity_confirmed",
                }
                or score >= 70
            )
            if not high_risk:
                continue
            declared_missing = {
                str(field) for field in item.get("missing_fields", [])
            } if isinstance(item.get("missing_fields"), list) else set()
            field_missing = any(
                field in declared_missing
                or item.get(field) in (None, "", [], {}, "[MISSING]")
                for field in REQUIRED_HIGH_RISK_FIELDS
            )
            if field_missing:
                incomplete.append(str(item.get("finding_id") or item.get("id") or f"finding:{index + 1}"))
        return tuple(dict.fromkeys(incomplete))

    @staticmethod
    def _integrity_valid(report: ReportSnapshot) -> bool:
        if not report.integrity_hash:
            return False
        return report.with_integrity().integrity_hash == report.integrity_hash
