"""Structured external intelligence and applicability scoring.

Online search adapters in the legacy agent return dictionaries with slightly
different shapes.  This module is the normalization boundary: every record
gets a source chain, an applicability decision and an explainable score before
it can influence planning.  A record is a hypothesis; execution evidence is
still required before a finding can become verified.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Literal, cast

from pydantic import Field

from .contracts import ContractModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_text(value: Any, limit: int = 2000) -> str:
    return str(value or "").strip()[:limit]


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


class IntelligenceSource(ContractModel):
    source_id: str = Field(min_length=1, max_length=240)
    kind: Literal["builtin", "skill", "experience", "online", "model", "human"] = "online"
    title: str = ""
    locator: str = ""
    publisher: str = ""
    published_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=_now)
    credibility: float = Field(default=0.5, ge=0.0, le=1.0)
    digest: str = ""

    def canonical_id(self) -> str:
        return self.source_id or self.digest or self.locator


class IntelligenceRecord(ContractModel):
    record_id: str = Field(min_length=1, max_length=240)
    product: str = Field(default="", max_length=240)
    product_family: str = Field(default="", max_length=160)
    versions: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    risk: Literal["low", "medium", "high", "critical", "unknown"] = "unknown"
    validation_evidence: list[str] = Field(default_factory=list)
    references: list[IntelligenceSource] = Field(default_factory=list)
    published_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=_now)
    raw_hash: str = ""
    sanitized_summary: str = ""
    known_pseudocode: bool = False
    applicability: Literal["unknown", "compatible", "mismatch", "unsupported"] = "unknown"
    applicability_reason: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @property
    def source_chain(self) -> list[str]:
        return [source.canonical_id() for source in self.references if source.canonical_id()]

    @property
    def has_validation_evidence(self) -> bool:
        return bool(self.validation_evidence) and not self.known_pseudocode


class IntelligenceCandidate(ContractModel):
    candidate_id: str
    record_id: str
    status: Literal["SUSPECTED", "CANDIDATE", "INCONCLUSIVE", "BLOCKED"] = "SUSPECTED"
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    risk: Literal["low", "medium", "high", "critical", "unknown"] = "unknown"
    product: str = ""
    preconditions: list[str] = Field(default_factory=list)
    expected_evidence: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    target_fingerprint: dict[str, str] = Field(default_factory=dict)


class IntelligenceParser:
    """Normalize NVD/MSF/Skill/experience shaped data into one record."""

    _IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    _HOST = re.compile(r"\b(?:[a-z0-9-]+\.)+(?:local|internal|test|example|com|net|org)\b", re.I)
    _SECRET = re.compile(r"(?i)\b(?:password|passwd|token|api[_-]?key|secret)\s*[:=]\s*[^\s,;]+")
    _PATH = re.compile(r"(?i)(?:/home|/root|/var/log|C:\\\\Users)[^\s`\"']*")
    _PSEUDOCODE = re.compile(r"(?i)\b(?:pseudocode|not tested|proof[- ]of[- ]concept only|example only|adapt as needed)\b")
    _VERSION = re.compile(r"(?<!\d)(\d+(?:\.\d+){0,3})(?!\d)")

    @classmethod
    def sanitize(cls, value: Any) -> str:
        text = _as_text(value, 20_000)
        text = cls._SECRET.sub("SECRET_REF=REDACTED", text)
        text = cls._IP.sub("TARGET_IP", text)
        text = cls._HOST.sub("TARGET_HOST", text)
        text = cls._PATH.sub("TARGET_PATH", text)
        return text

    @classmethod
    def _source(cls, raw: dict[str, Any], source: IntelligenceSource | None) -> IntelligenceSource:
        if source is not None:
            return source
        locator = _as_text(raw.get("url") or raw.get("source_url") or raw.get("reference") or raw.get("source"), 500)
        title = _as_text(raw.get("title") or raw.get("cve_id") or raw.get("module_name") or raw.get("product"), 240)
        kind = str(raw.get("source_kind", "online")).lower()
        if kind not in {"builtin", "skill", "experience", "online", "model", "human"}:
            kind = "online"
        credibility = raw.get("credibility", raw.get("source_credibility", 0.6))
        try:
            credibility = max(0.0, min(1.0, float(credibility)))
        except (TypeError, ValueError):
            credibility = 0.6
        digest = hashlib.sha256(cls.sanitize(raw).encode()).hexdigest()
        return IntelligenceSource(
            source_id=_as_text(raw.get("source_id") or locator or digest[:24], 240),
            kind=cast(Literal["builtin", "skill", "experience", "online", "model", "human"], kind),
            title=title,
            locator=locator,
            publisher=_as_text(raw.get("publisher") or raw.get("source"), 160),
            published_at=_parse_datetime(raw.get("published") or raw.get("published_at") or raw.get("date")),
            credibility=credibility,
            digest=digest,
        )

    @classmethod
    def parse(cls, raw: dict[str, Any] | str, *, source: IntelligenceSource | None = None) -> IntelligenceRecord:
        if isinstance(raw, str):
            raw_map: dict[str, Any] = {"description": raw}
        else:
            raw_map = dict(raw or {})
        nested = raw_map.get("data")
        if isinstance(nested, dict):
            merged = dict(nested)
            merged.update({key: value for key, value in raw_map.items() if key != "data"})
            raw_map = merged
        source_ref = cls._source(raw_map, source)
        product = _as_text(
            raw_map.get("product")
            or raw_map.get("service")
            or raw_map.get("keyword")
            or raw_map.get("vendor_product")
            or raw_map.get("module_name")
        )
        versions: list[str] = []
        version_values = raw_map.get("versions") or raw_map.get("affected_versions") or raw_map.get("version")
        if isinstance(version_values, (list, tuple, set)):
            versions.extend(_as_text(item, 120) for item in version_values)
        elif version_values:
            versions.append(_as_text(version_values, 120))
        for item in raw_map.get("affected_products", []) or []:
            if isinstance(item, dict):
                cpe = _as_text(item.get("cpe") or item.get("product"), 300)
                versions.extend(cls._VERSION.findall(cpe))
                for key in ("version_start", "version_end"):
                    if item.get(key):
                        versions.append(_as_text(item[key], 80))
            else:
                versions.extend(cls._VERSION.findall(_as_text(item, 300)))
        versions = list(dict.fromkeys(item for item in versions if item))[:40]
        platforms = raw_map.get("platforms") or raw_map.get("platform") or raw_map.get("os") or []
        if isinstance(platforms, str):
            platforms = [platforms]
        platforms = list(dict.fromkeys(_as_text(item, 100).lower() for item in platforms if _as_text(item, 100)))[:20]
        prerequisites = raw_map.get("prerequisites") or raw_map.get("preconditions") or raw_map.get("requirements") or []
        if isinstance(prerequisites, str):
            prerequisites = [prerequisites]
        prerequisites = [cls.sanitize(item) for item in prerequisites if _as_text(item)]
        evidence = raw_map.get("validation_evidence") or raw_map.get("verification_evidence") or raw_map.get("evidence") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        if raw_map.get("exploit_available") is True:
            evidence.append("source reports a published exploit/module reference")
        evidence = list(dict.fromkeys(cls.sanitize(item) for item in evidence if _as_text(item)))[:30]
        description = cls.sanitize(raw_map.get("description") or raw_map.get("principle_cn") or raw_map.get("exploit_guide") or "")
        if description and not evidence and raw_map.get("references"):
            refs = raw_map.get("references")
            if isinstance(refs, list) and any(isinstance(item, dict) and item.get("tags") for item in refs):
                evidence.append("reference metadata is available; runtime validation remains required")
        cvss = raw_map.get("cvss_score") or raw_map.get("cvss") or 0
        try:
            cvss_value = float(cvss)
        except (TypeError, ValueError):
            cvss_value = 0.0
        if cvss_value >= 9:
            risk = "critical"
        elif cvss_value >= 7:
            risk = "high"
        elif cvss_value >= 4:
            risk = "medium"
        elif cvss_value > 0:
            risk = "low"
        else:
            risk = str(raw_map.get("risk", "unknown")).lower()
            if risk not in {"low", "medium", "high", "critical", "unknown"}:
                risk = "unknown"
        raw_hash = hashlib.sha256(cls.sanitize(raw_map).encode()).hexdigest()
        record_id = _as_text(raw_map.get("record_id") or raw_map.get("cve_id") or raw_map.get("module_name") or raw_hash[:24], 240)
        published = _parse_datetime(raw_map.get("published") or raw_map.get("published_at") or raw_map.get("date"))
        return IntelligenceRecord(
            record_id=record_id,
            product=product,
            product_family=_as_text(raw_map.get("product_family") or raw_map.get("family"), 160),
            versions=versions,
            platforms=platforms,
            prerequisites=prerequisites,
            risk=cast(Literal["low", "medium", "high", "critical", "unknown"], risk),
            validation_evidence=evidence,
            references=[source_ref],
            published_at=published or source_ref.published_at,
            raw_hash=raw_hash,
            sanitized_summary=description[:4000],
            known_pseudocode=bool(raw_map.get("known_pseudocode")) or bool(cls._PSEUDOCODE.search(description)),
        )


class IntelligenceScorer:
    """Applicability and source quality scorer used by the planner boundary."""

    def __init__(self, *, half_life_days: int = 365, high_risk_threshold: float = 0.72):
        self.half_life_days = max(1, int(half_life_days))
        self.high_risk_threshold = max(0.0, min(1.0, float(high_risk_threshold)))

    @staticmethod
    def _version_parts(value: str) -> tuple[int, ...]:
        match = re.search(r"\d+(?:\.\d+){0,3}", str(value))
        if not match:
            return ()
        return tuple(int(part) for part in match.group(0).split("."))

    def _version_match(self, observed: str, versions: list[str]) -> bool | None:
        if not versions:
            return None
        observed_parts = self._version_parts(observed)
        if not observed_parts:
            return None
        for candidate in versions:
            text = str(candidate).strip().lower()
            if observed.lower() in text or text in observed.lower():
                return True
            parts = self._version_parts(text)
            if parts and observed_parts[: len(parts)] == parts:
                return True
        return False

    def applicability(self, record: IntelligenceRecord, target: dict[str, Any]) -> tuple[str, str]:
        product = _as_text(target.get("product") or target.get("service") or target.get("banner"), 240).lower()
        platform = _as_text(target.get("platform") or target.get("os"), 120).lower()
        observed_version = _as_text(target.get("version"), 120)
        if record.product and product:
            product_tokens = set(re.findall(r"[a-z0-9][a-z0-9._-]+", record.product.lower()))
            target_tokens = set(re.findall(r"[a-z0-9][a-z0-9._-]+", product))
            generic = {"server", "service", "product", "software", "http", "https", "application", "app"}
            product_tokens -= generic
            target_tokens -= generic
            if product_tokens and target_tokens and not (product_tokens & target_tokens):
                return "mismatch", "product fingerprint does not match"
        version_match = self._version_match(observed_version, record.versions)
        if version_match is False:
            return "mismatch", "observed version is outside the published version set"
        if record.platforms and platform and not any(item in platform or platform in item for item in record.platforms):
            return "unsupported", "target platform is not covered by the source"
        if record.known_pseudocode:
            return "unknown", "source is marked as untested or pseudocode"
        if not product and not observed_version and not platform:
            return "unknown", "target fingerprint is incomplete"
        return "compatible", "fingerprint is compatible or sufficiently specific"

    def score(
        self,
        record: IntelligenceRecord,
        target: dict[str, Any],
        *,
        peers: Sequence[IntelligenceRecord] = (),
    ) -> IntelligenceCandidate:
        applicability, applicability_reason = self.applicability(record, target)
        record = record.model_copy(update={"applicability": applicability, "applicability_reason": applicability_reason})
        if applicability in {"mismatch", "unsupported"}:
            status: Literal["SUSPECTED", "CANDIDATE", "INCONCLUSIVE", "BLOCKED"] = "INCONCLUSIVE"
        elif not record.has_validation_evidence:
            status = "SUSPECTED"
        else:
            status = "CANDIDATE"
        now = _now()
        age_days = max(0.0, (now - (record.published_at or record.retrieved_at)).total_seconds() / 86400)
        freshness = math.exp(-math.log(2) * age_days / self.half_life_days)
        credibility = sum(source.credibility for source in record.references) / max(1, len(record.references))
        matching_peers = 0
        for peer in peers:
            if peer.product.lower() == record.product.lower() and peer.record_id != record.record_id:
                matching_peers += 1
        agreement = min(1.0, 0.5 + 0.15 * matching_peers)
        applicability_score = {"compatible": 1.0, "unknown": 0.35, "mismatch": 0.0, "unsupported": 0.0}[applicability]
        validation_score = 1.0 if record.has_validation_evidence else 0.2
        score = max(0.0, min(1.0, 0.28 * credibility + 0.18 * freshness + 0.22 * agreement + 0.22 * applicability_score + 0.10 * validation_score))
        rationale = [applicability_reason, f"source credibility={credibility:.2f}", f"freshness={freshness:.2f}", f"source agreement={agreement:.2f}"]
        if record.known_pseudocode:
            rationale.append("untested source cannot support a verified conclusion")
        if record.risk in {"high", "critical"} and score < self.high_risk_threshold:
            rationale.append("high-risk action remains gated because source confidence is below threshold")
        candidate_id = "candidate_" + hashlib.sha256(f"{record.record_id}:{target}".encode()).hexdigest()[:24]
        expected = ["runtime reproduction", "typed evidence rule", "target-bound response"]
        return IntelligenceCandidate(
            candidate_id=candidate_id,
            record_id=record.record_id,
            status=status,
            score=score,
            risk=record.risk,
            product=record.product,
            preconditions=list(record.prerequisites),
            expected_evidence=expected,
            source_refs=record.source_chain,
            rationale=rationale,
            target_fingerprint={key: _as_text(value, 240) for key, value in target.items() if value is not None},
        )


class IntelligenceCatalog:
    """Small deterministic catalog for state snapshots and planner queries."""

    def __init__(self, scorer: IntelligenceScorer | None = None):
        self.scorer = scorer or IntelligenceScorer()
        self.records: dict[str, IntelligenceRecord] = {}

    def add(self, record: IntelligenceRecord | dict[str, Any] | str, *, source: IntelligenceSource | None = None) -> IntelligenceRecord:
        normalized = record if isinstance(record, IntelligenceRecord) else IntelligenceParser.parse(record, source=source)
        current = self.records.get(normalized.record_id)
        if current is not None:
            refs = {item.canonical_id(): item for item in current.references + normalized.references}
            normalized = normalized.model_copy(update={"references": list(refs.values()), "confidence": max(current.confidence, normalized.confidence)})
        self.records[normalized.record_id] = normalized
        return normalized

    def candidates(self, target: dict[str, Any]) -> list[IntelligenceCandidate]:
        records = list(self.records.values())
        return sorted(
            (self.scorer.score(record, target, peers=records) for record in records),
            key=lambda item: (-item.score, item.candidate_id),
        )

    def as_dict(self) -> dict[str, Any]:
        return {key: value.model_dump(mode="json") for key, value in sorted(self.records.items())}


__all__ = [
    "IntelligenceSource",
    "IntelligenceRecord",
    "IntelligenceCandidate",
    "IntelligenceParser",
    "IntelligenceScorer",
    "IntelligenceCatalog",
]
