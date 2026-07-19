from __future__ import annotations

import hashlib
import json
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
    # Canonical PRD truth states.  Legacy states remain readable below so
    # persisted 0.55 snapshots can be migrated without inventing evidence.
    NOT_STARTED = "NOT_STARTED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"
    UNREACHABLE = "UNREACHABLE"
    UNOBSERVED = "UNOBSERVED"
    DISCOVERED = "DISCOVERED"
    ENUMERATED = "ENUMERATED"
    POTENTIALLY_VULNERABLE = "POTENTIALLY_VULNERABLE"
    VULNERABILITY_CONFIRMED = "VULNERABILITY_CONFIRMED"
    EXPLOIT_TRIGGERED = "EXPLOIT_TRIGGERED"
    SUSPECTED = "SUSPECTED"
    CANDIDATE = "CANDIDATE"
    ATTEMPTED = "ATTEMPTED"
    VERIFIED_VULNERABLE = "VERIFIED_VULNERABLE"
    EXPLOITED = "EXPLOITED"
    SESSION_ESTABLISHED = "SESSION_ESTABLISHED"
    IDENTITY_CONFIRMED = "IDENTITY_CONFIRMED"
    PRIVILEGE_CONFIRMED = "PRIVILEGE_CONFIRMED"
    OBJECTIVE_COMPLETED = "OBJECTIVE_COMPLETED"
    FAILED = "FAILED"
    INCONCLUSIVE = "INCONCLUSIVE"
    CANCELLED = "CANCELLED"
    EVIDENCE_COMPLETE = "EVIDENCE_COMPLETE"
    EXHAUSTED = "EXHAUSTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PolicyDecisionKind(str, Enum):
    ALLOW = "ALLOW"
    ALLOW_WITH_LIMITS = "ALLOW_WITH_LIMITS"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


class AutonomyMode(str, Enum):
    ADVISORY = "advisory"
    SUPERVISED = "supervised"
    UNATTENDED = "unattended"


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

    model_config = ConfigDict(extra="forbid", use_enum_values=True, frozen=True)

    scope_id: str = Field(default_factory=lambda: f"scope_{uuid4().hex}", min_length=8, max_length=128)
    mission_id: str = Field(default_factory=lambda: f"mission_{uuid4().hex}", min_length=8, max_length=128)
    owner: str = Field(min_length=1, max_length=160)
    authorization_subject: str = Field(default="local-fixture", min_length=1, max_length=240)
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
    allowed_test_types: set[str] = Field(
        default_factory=lambda: {"discovery", "enumeration", "verification", "session_verification"}
    )
    forbidden_operations: set[str] = Field(
        default_factory=lambda: {
            "persistence",
            "destructive_write",
            "denial_of_service",
            "log_clearing",
            "scope_expansion",
        }
    )
    starts_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    max_concurrency: int = Field(default=1, ge=1, le=64)
    max_duration_seconds: int = Field(default=3600, ge=1, le=604800)
    max_commands: int = Field(default=1000, ge=1, le=100000)
    max_network_requests: int = Field(default=10000, ge=1, le=1000000)
    max_requests_per_second: float = Field(default=10.0, gt=0, le=10000)
    max_request_burst: int = Field(default=20, ge=1, le=100000)
    max_llm_tokens: int = Field(default=120000, ge=0, le=100000000)
    max_bruteforce_attempts: int = Field(default=100, ge=0, le=1000000)
    max_storage_bytes: int = Field(default=268435456, ge=0, le=1099511627776)
    allow_credentials: bool = False
    allow_uploads: bool = False
    allow_sessions: bool = True
    allow_privilege_validation: bool = False
    emergency_stop: bool = False
    autonomy_mode: AutonomyMode = AutonomyMode.SUPERVISED
    data_handling: Literal["ephemeral", "task_retained", "organization_retained"] = "ephemeral"
    retention_seconds: int = Field(default=86400, ge=0, le=315360000)
    purpose: str = Field(default="authorized teaching assessment", max_length=500)
    policy_version: str = Field(default="scope.v1", min_length=1, max_length=32)
    policy_template_id: str = Field(default="", max_length=128)
    policy_template_version: str = Field(default="", max_length=64)
    policy_template_hash: str = Field(default="", max_length=128)
    revision: int = Field(default=1, ge=1)

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

    @field_validator("allowed_protocols", "allowed_test_types", "forbidden_operations")
    @classmethod
    def normalize_policy_values(cls, values):
        return type(values)(str(value).strip().lower() for value in values if str(value).strip())

    def canonical_hash(self) -> str:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ActionEnvelope(ContractModel):
    """Immutable-ish description produced before an executor runs."""

    action_id: str = Field(default_factory=lambda: f"action_{uuid4().hex}")
    task_id: str = Field(min_length=1, max_length=128)
    mission_id: str = Field(default="mission-local", min_length=1, max_length=128)
    scope_id: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    protocol: str = Field(default="tcp", min_length=1, max_length=16)
    plugin: str = Field(min_length=1, max_length=160)
    plugin_version: str = Field(default="0", max_length=64)
    action_level: ActionLevel
    intent: str = Field(min_length=1, max_length=500)
    expected_evidence: list[str] = Field(default_factory=list, min_length=1)
    params_hash: str = Field(default="", max_length=128)
    normalized_params: dict[str, Any] = Field(default_factory=dict)
    source: str = Field(default="planner", min_length=1, max_length=120)
    scope_result: PolicyDecisionKind | None = None
    rollback: str = Field(default="terminate process and release resources", max_length=500)
    cleanup: list[str] = Field(default_factory=list)
    command_hash: str = Field(default="", max_length=128)
    request_hash: str = Field(default="", max_length=128)
    parent_action_id: str | None = Field(default=None, max_length=128)
    idempotency_key: str = Field(default_factory=lambda: f"idem_{uuid4().hex}", min_length=8, max_length=160)
    risk: Literal["low", "medium", "high", "critical"] = "low"
    budget_cost: dict[str, int] = Field(default_factory=dict)
    dry_run: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class EvidenceRecord(ContractModel):
    evidence_id: str = Field(default_factory=lambda: f"evidence_{uuid4().hex}")
    task_id: str
    mission_id: str = "mission-local"
    target: str
    target_id: str = ""
    evidence_type: str
    status: EvidenceStatus
    rule_id: str
    rule_version: str = "evidence.v1"
    raw_hash: str = Field(min_length=16, max_length=128)
    raw_ref: str = ""
    artifact_ref: str = ""
    normalized: dict[str, Any] = Field(default_factory=dict)
    action_id: str | None = None
    source: Literal["tool", "session", "reproduction", "human", "model"] = "tool"
    source_type: str = "tool"
    source_name: str = ""
    source_version: str = ""
    command_hash: str = ""
    request_hash: str = ""
    sanitized_command: str = ""
    sanitized_request: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reproducible: bool | None = None
    reproduction_count: int = Field(default=0, ge=0)
    judge_id: str = ""
    judge_version: str = ""
    judge_result: dict[str, Any] = Field(default_factory=dict)
    scope_decision: PolicyDecisionKind | None = None
    parent_evidence_ids: list[str] = Field(default_factory=list)
    negative: bool = False
    conflict: bool = False
    sensitivity: Literal["public", "internal", "sensitive", "secret"] = "internal"
    retention_policy: str = "task-default"
    integrity: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=utc_now)


class FindingRecord(ContractModel):
    finding_id: str = Field(default_factory=lambda: f"finding_{uuid4().hex}")
    task_id: str
    title: str
    target: str
    status: EvidenceStatus = EvidenceStatus.UNOBSERVED
    severity: Literal["info", "low", "medium", "high", "critical"] = "info"
    impact: str = ""
    asset_links: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    negative_evidence_ids: list[str] = Field(default_factory=list)
    conflict_evidence_ids: list[str] = Field(default_factory=list)
    status_reason: str = ""
    judge_id: str = ""
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
    previous_state: str | None = None
    new_state: str | None = None
    reason: str = ""
    rule_version: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    idempotency_key: str = ""
    previous_hash: str = ""
    event_hash: str = ""
