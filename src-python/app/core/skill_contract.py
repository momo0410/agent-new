"""Skill manifest, provenance and promotion gate."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import Field

from .contracts import ContractModel


class SkillManifest(ContractModel):
    skill_id: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=64)
    author: str = Field(min_length=1, max_length=160)
    origin: str = Field(min_length=1, max_length=500)
    applicable_scope: dict[str, Any] = Field(default_factory=dict)
    risk: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    dependencies: list[str] = Field(default_factory=list)
    evidence_rules: list[str] = Field(min_length=1)
    tests: list[str] = Field(min_length=1)
    lifecycle: str = "draft"
    signature: str = ""
    content_hash: str = ""
    source_refs: list[str] = Field(default_factory=list)
    environment_fingerprint: str = ""
    approved_by: str = ""


@dataclass(frozen=True)
class SkillEvaluationRecord:
    evaluation_id: str
    skill_id: str
    version: str
    static_check: bool
    sandbox: bool
    positive_samples: bool
    negative_samples: bool
    regression: bool
    generalization: bool
    security: bool
    metrics: dict[str, float] = field(default_factory=dict)
    source_refs: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return all((
            self.static_check,
            self.sandbox,
            self.positive_samples,
            self.negative_samples,
            self.regression,
            self.generalization,
            self.security,
        ))


class SkillContentScanner:
    PATTERNS = (
        re.compile(r"(?i)ignore (all|previous|system) instructions"),
        re.compile(r"(?i)reveal (the )?(system prompt|secret|token)"),
        re.compile(r"(?i)(password|api[_-]?key|token)\s*[:=]\s*[^\s]+"),
        re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----", re.I),
        re.compile(r"(?i)(<\|system\|>|<\|assistant\|>|\[INST\]|/no_think)"),
        re.compile(r"(?i)(disable|bypass|turn off)\s+(scope|policy|audit|approval)"),
    )

    def scan(self, content: str) -> list[str]:
        return [pattern.pattern for pattern in self.PATTERNS if pattern.search(str(content))]


@dataclass(frozen=True)
class SkillKnowledgeRecord:
    record_id: str
    kind: Literal["fact", "inference", "failure", "environment"]
    content: str
    source_refs: tuple[str, ...] = ()
    environment_fingerprint: str = ""
    confidence: float = 0.0
    approved_for_sharing: bool = False

    def shareable(self) -> bool:
        return self.approved_for_sharing and self.kind != "environment" and bool(self.source_refs)


class SkillKnowledgeFilter:
    """Classify and sanitize experience before it can enter a shared Skill."""

    _IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    _HOST = re.compile(r"\b(?:[a-z0-9-]+\.)+(?:local|internal|test|example|com|net|org)\b", re.I)
    _PATH = re.compile(r"(?i)(?:/home|/root|C:\\\\Users|/var/log)/[^\s`]+")

    def __init__(self, scanner: SkillContentScanner | None = None):
        self.scanner = scanner or SkillContentScanner()

    def classify(
        self,
        content: str,
        *,
        source_refs: tuple[str, ...] = (),
        environment_fingerprint: str = "",
        kind: Literal["fact", "inference", "failure", "environment"] = "fact",
        confidence: float = 0.5,
        approved_for_sharing: bool = False,
    ) -> SkillKnowledgeRecord:
        return SkillKnowledgeRecord(
            record_id="knowledge_" + hashlib.sha256(str(content).encode()).hexdigest()[:24],
            kind=kind,
            content=self.sanitize(content),
            source_refs=tuple(str(item) for item in source_refs if str(item)),
            environment_fingerprint=str(environment_fingerprint),
            confidence=max(0.0, min(1.0, float(confidence))),
            approved_for_sharing=bool(approved_for_sharing) and not self.scanner.scan(content),
        )

    @classmethod
    def sanitize(cls, content: str) -> str:
        value = str(content)
        value = cls._IP.sub("TARGET_IP", value)
        value = cls._HOST.sub("TARGET_HOST", value)
        value = cls._PATH.sub("TARGET_PATH", value)
        return value[:20_000]

    def validate_for_promotion(self, records: list[SkillKnowledgeRecord]) -> list[str]:
        reasons: list[str] = []
        for record in records:
            if not record.source_refs:
                reasons.append(f"knowledge record {record.record_id} has no source chain")
            if record.kind == "environment":
                reasons.append(f"environment-specific record {record.record_id} cannot enter shared Skill")
            if not record.shareable():
                reasons.append(f"knowledge record {record.record_id} is not approved for sharing")
            if self.scanner.scan(record.content):
                reasons.append(f"knowledge record {record.record_id} contains unsafe instructions")
        return list(dict.fromkeys(reasons))


class SkillPromotionGate:
    def __init__(self, scanner: SkillContentScanner | None = None, knowledge_filter: SkillKnowledgeFilter | None = None):
        self.scanner = scanner or SkillContentScanner()
        self.knowledge_filter = knowledge_filter or SkillKnowledgeFilter(self.scanner)

    def check(
        self,
        manifest: SkillManifest,
        evaluation: SkillEvaluationRecord | None,
        *,
        content: str = "",
        knowledge_records: list[SkillKnowledgeRecord] | None = None,
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if manifest.lifecycle not in {"draft", "evaluating", "canary"}:
            reasons.append("only a pre-active skill may be promoted")
        if evaluation is None or evaluation.skill_id != manifest.skill_id or evaluation.version != manifest.version:
            reasons.append("matching evaluation record is required")
        elif not evaluation.passed:
            reasons.append("evaluation suite is incomplete")
        findings = self.scanner.scan(content)
        if findings:
            reasons.append("content scanner found untrusted instructions or sensitive material")
        if manifest.content_hash and content:
            digest = hashlib.sha256(content.encode()).hexdigest()
            if digest != manifest.content_hash:
                reasons.append("skill content hash mismatch")
        if not manifest.source_refs and not manifest.origin:
            reasons.append("skill provenance source chain is required")
        if knowledge_records:
            reasons.extend(self.knowledge_filter.validate_for_promotion(knowledge_records))
        return not reasons, reasons
