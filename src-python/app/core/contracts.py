from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class ActionLevel(str, Enum):
    OBSERVE = "observe"
    PROBE = "probe"
    CREDENTIAL_TEST = "credential_test"
    EXPLOIT = "exploit"
    SESSION_VERIFY = "session_verify"
    POST_VERIFY = "post_verify"
    PROHIBITED = "prohibited"


class EvidenceStatus(str, Enum):
    UNOBSERVED = "UNOBSERVED"
    DISCOVERED = "DISCOVERED"
    SUSPECTED = "SUSPECTED"
    CANDIDATE = "CANDIDATE"
    ATTEMPTED = "ATTEMPTED"
    VERIFIED_VULNERABLE = "VERIFIED_VULNERABLE"
    EXPLOITED = "EXPLOITED"
    SESSION_ESTABLISHED = "SESSION_ESTABLISHED"
    PRIVILEGE_CONFIRMED = "PRIVILEGE_CONFIRMED"
    EVIDENCE_COMPLETE = "EVIDENCE_COMPLETE"
    EXHAUSTED = "EXHAUSTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PortRange(ContractModel):
    start: int = Field(ge=1, le=65535)
    end: int = Field(ge=1, le=65535)

    def contains(self, port: int) -> bool:
        return self.start <= port <= self.end

    @field_validator("end")
    @classmethod
    def validate_order(cls, value: int, info):
        start = info.data.get("start")
        if start is not None and value < start:
            raise ValueError("port range end must be >= start")
        return value


class ScopeContract(ContractModel):
    """Machine-enforceable task scope and resource policy."""

    scope_id: str = Field(default_factory=lambda: f"scope_{uuid4().hex}", min_length=8, max_length=128)
    owner: str = Field(min_length=1, max_length=160)
    allowed_targets: list[str] = Field(default_factory=list, min_length=1)
    allowed_cidrs: list[str] = Field(default_factory=list)
    allowed_domains: list[str] = Field(default_factory=list)
    allowed_ports: list[int] = Field(default_factory=list)
    allowed_port_ranges: list[PortRange] = Field(default_factory=list)
    allowed_protocols: list[str] = Field(default_factory=lambda: ["tcp"])
    allowed_actions: set[ActionLevel] = Field(
        default_factory=lambda: {
            ActionLevel.OBSERVE,
            ActionLevel.PROBE,
            ActionLevel.CREDENTIAL_TEST,
            ActionLevel.EXPLOIT,
            ActionLevel.SESSION_VERIFY,
            ActionLevel.POST_VERIFY,
        }
    )
    forbidden_actions: set[ActionLevel] = Field(default_factory=lambda: {ActionLevel.PROHIBITED})
    starts_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    max_concurrency: int = Field(default=1, ge=1, le=64)
    max_duration_seconds: int = Field(default=3600, ge=1, le=604800)
    max_commands: int = Field(default=1000, ge=1, le=100000)
    max_network_requests: int = Field(default=10000, ge=1, le=1000000)
    data_handling: Literal["ephemeral", "task_retained", "organization_retained"] = "ephemeral"
    purpose: str = Field(default="authorized teaching assessment", max_length=500)
    policy_version: str = Field(default="scope.v1", min_length=1, max_length=32)

    @field_validator("allowed_targets", "allowed_cidrs", "allowed_domains", "allowed_protocols")
    @classmethod
    def strip_values(cls, values: list[str]) -> list[str]:
        return [str(value).strip() for value in values if str(value).strip()]

    @field_validator("allowed_ports")
    @classmethod
    def validate_ports(cls, values: list[int]) -> list[int]:
        if any(port < 1 or port > 65535 for port in values):
            raise ValueError("allowed_ports must be between 1 and 65535")
        return sorted(set(values))


class ActionEnvelope(ContractModel):
    """Immutable-ish description produced before an executor runs."""

    action_id: str = Field(default_factory=lambda: f"action_{uuid4().hex}")
    task_id: str = Field(min_length=1, max_length=128)
    scope_id: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    protocol: str = Field(default="tcp", min_length=1, max_length=16)
    plugin: str = Field(min_length=1, max_length=160)
    action_level: ActionLevel
    intent: str = Field(min_length=1, max_length=500)
    expected_evidence: list[str] = Field(default_factory=list, min_length=1)
    params_hash: str = Field(default="", max_length=128)
    risk: Literal["low", "medium", "high"] = "low"
    budget_cost: dict[str, int] = Field(default_factory=dict)
    dry_run: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class EvidenceRecord(ContractModel):
    evidence_id: str = Field(default_factory=lambda: f"evidence_{uuid4().hex}")
    task_id: str
    target: str
    evidence_type: str
    status: EvidenceStatus
    rule_id: str
    rule_version: str = "evidence.v1"
    raw_hash: str = Field(min_length=16, max_length=128)
    normalized: dict[str, Any] = Field(default_factory=dict)
    action_id: str | None = None
    source: Literal["tool", "session", "reproduction", "human", "model"] = "tool"
    evidence_refs: list[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=utc_now)


class FindingRecord(ContractModel):
    finding_id: str = Field(default_factory=lambda: f"finding_{uuid4().hex}")
    task_id: str
    title: str
    target: str
    status: EvidenceStatus = EvidenceStatus.UNOBSERVED
    severity: Literal["info", "low", "medium", "high", "critical"] = "info"
    evidence_ids: list[str] = Field(default_factory=list)
    negative_evidence_ids: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)


class EventEnvelope(ContractModel):
    schema_version: str = "event.v1"
    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex}")
    task_id: str = Field(min_length=1, max_length=128)
    sequence: int = Field(ge=1)
    timestamp: datetime = Field(default_factory=utc_now)
    event_type: str = Field(min_length=1, max_length=120)
    actor: str = Field(default="system", min_length=1, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)
    previous_hash: str = ""
    event_hash: str = ""

