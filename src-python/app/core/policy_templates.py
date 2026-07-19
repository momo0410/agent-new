"""Immutable course policy templates and narrowing validation."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import threading
from datetime import datetime, timezone
from typing import Any

from pydantic import ConfigDict, Field

from .contracts import AutonomyMode, ContractModel, ScopeContract, utc_now


class CoursePolicyError(ValueError):
    """Raised when a task scope expands beyond its course template."""


class CoursePolicyTemplate(ContractModel):
    """Versioned administrator-owned upper bound for student task scopes."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True, frozen=True)

    template_id: str = Field(min_length=3, max_length=128)
    version: str = Field(default="1.0.0", min_length=1, max_length=64)
    owner: str = Field(min_length=1, max_length=160)
    scope_ceiling: ScopeContract
    created_at: datetime = Field(default_factory=utc_now)
    supersedes: str = Field(default="", max_length=64)
    notes: str = Field(default="", max_length=1000)

    def canonical_hash(self) -> str:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def violations(self, scope: ScopeContract) -> list[str]:
        ceiling = self.scope_ceiling
        failures: list[str] = []
        if scope.policy_template_id != self.template_id:
            failures.append("policy template id mismatch")
        if scope.policy_template_version != self.version:
            failures.append("policy template version mismatch")
        if scope.policy_template_hash != self.canonical_hash():
            failures.append("policy template hash mismatch")

        exact_targets = {_host(item) for item in ceiling.allowed_targets}
        if any(_host(item) not in exact_targets for item in scope.allowed_targets):
            failures.append("allowed targets expand the course template")
        if any(not _cidr_within(item, ceiling.allowed_cidrs) for item in scope.allowed_cidrs):
            failures.append("allowed CIDRs expand the course template")
        if any(not _domain_within(item, ceiling.allowed_domains) for item in scope.allowed_domains):
            failures.append("allowed domains expand the course template")
        if any(not _port_covered(port, ceiling) for port in scope.allowed_ports):
            failures.append("allowed ports expand the course template")
        if any(
            not _range_covered(item.start, item.end, ceiling)
            for item in scope.allowed_port_ranges
        ):
            failures.append("allowed port ranges expand the course template")

        _require_subset(failures, "protocols", scope.allowed_protocols, ceiling.allowed_protocols)
        _require_subset(failures, "actions", scope.allowed_actions, ceiling.allowed_actions)
        _require_subset(failures, "test types", scope.allowed_test_types, ceiling.allowed_test_types)
        if not {_policy_value(item) for item in ceiling.forbidden_actions}.issubset(
            {_policy_value(item) for item in scope.forbidden_actions}
        ):
            failures.append("required forbidden actions were removed")
        if not set(ceiling.forbidden_operations).issubset(set(scope.forbidden_operations)):
            failures.append("required forbidden operations were removed")

        if _aware(scope.starts_at) < _aware(ceiling.starts_at):
            failures.append("task starts before the course window")
        if _aware(scope.expires_at) > _aware(ceiling.expires_at):
            failures.append("task expires after the course window")
        if scope.max_duration_seconds > ceiling.max_duration_seconds:
            failures.append("duration budget expands the course template")

        numeric_limits = (
            "max_concurrency", "max_commands", "max_network_requests",
            "max_requests_per_second", "max_request_burst", "max_llm_tokens",
            "max_bruteforce_attempts", "max_storage_bytes", "retention_seconds",
        )
        for field_name in numeric_limits:
            if getattr(scope, field_name) > getattr(ceiling, field_name):
                failures.append(f"{field_name} expands the course template")

        for field_name in (
            "allow_credentials", "allow_uploads", "allow_sessions", "allow_privilege_validation",
        ):
            if bool(getattr(scope, field_name)) and not bool(getattr(ceiling, field_name)):
                failures.append(f"{field_name} expands the course template")

        autonomy_rank = {
            AutonomyMode.ADVISORY.value: 0,
            AutonomyMode.SUPERVISED.value: 1,
            AutonomyMode.UNATTENDED.value: 2,
        }
        if autonomy_rank[_policy_value(scope.autonomy_mode)] > autonomy_rank[_policy_value(ceiling.autonomy_mode)]:
            failures.append("autonomy mode expands the course template")
        retention_rank = {"ephemeral": 0, "task_retained": 1, "organization_retained": 2}
        if retention_rank[scope.data_handling] > retention_rank[ceiling.data_handling]:
            failures.append("data handling expands the course template")
        return list(dict.fromkeys(failures))

    def enforce(self, scope: ScopeContract) -> None:
        failures = self.violations(scope)
        if failures:
            raise CoursePolicyError("; ".join(failures))


class CoursePolicyRegistry:
    """Thread-safe append-only registry; published versions remain immutable."""

    ADMIN_ROLES = frozenset({"course_admin", "administrator"})

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._templates: dict[tuple[str, str], CoursePolicyTemplate] = {}
        self._audit: list[dict[str, Any]] = []

    def publish(self, template: CoursePolicyTemplate, *, actor: str, actor_role: str) -> CoursePolicyTemplate:
        if str(actor_role).strip().lower() not in self.ADMIN_ROLES:
            raise CoursePolicyError("course policy publication requires an administrator role")
        key = (template.template_id, template.version)
        with self._lock:
            existing = self._templates.get(key)
            if existing and existing.canonical_hash() != template.canonical_hash():
                raise CoursePolicyError("published course policy versions are immutable")
            self._templates[key] = template
            self._audit.append({
                "event": "course_policy.published",
                "template_id": template.template_id,
                "version": template.version,
                "template_hash": template.canonical_hash(),
                "actor": str(actor),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        return template

    def get(self, template_id: str, version: str) -> CoursePolicyTemplate:
        with self._lock:
            try:
                return self._templates[(str(template_id), str(version))]
            except KeyError as exc:
                raise CoursePolicyError("course policy template was not found") from exc

    def enforce(self, scope: ScopeContract) -> CoursePolicyTemplate:
        if not scope.policy_template_id or not scope.policy_template_version:
            raise CoursePolicyError("task scope has no course policy binding")
        template = self.get(scope.policy_template_id, scope.policy_template_version)
        template.enforce(scope)
        return template

    def bind(
        self,
        template_id: str,
        version: str,
        values: dict[str, Any],
        *,
        actor: str = "student",
        actor_role: str = "student",
    ) -> ScopeContract:
        template = self.get(template_id, version)
        payload = template.scope_ceiling.model_dump()
        payload.update(dict(values))
        payload.update({
            "policy_template_id": template.template_id,
            "policy_template_version": template.version,
            "policy_template_hash": template.canonical_hash(),
        })
        scope = ScopeContract.model_validate(payload)
        template.enforce(scope)
        with self._lock:
            self._audit.append({
                "event": "course_policy.bound",
                "template_id": template.template_id,
                "version": template.version,
                "template_hash": template.canonical_hash(),
                "actor": str(actor),
                "actor_role": str(actor_role),
                "scope_id": scope.scope_id,
                "scope_hash": scope.canonical_hash(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        return scope

    def audit_events(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._audit]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _host(value: str) -> str:
    return str(value or "").strip().lower().rstrip(".")


def _cidr_within(value: str, allowed: list[str]) -> bool:
    try:
        candidate = ipaddress.ip_network(str(value), strict=False)
    except ValueError:
        return False
    for item in allowed:
        try:
            parent = ipaddress.ip_network(str(item), strict=False)
        except ValueError:
            continue
        if (
            isinstance(candidate, ipaddress.IPv4Network)
            and isinstance(parent, ipaddress.IPv4Network)
            and candidate.subnet_of(parent)
        ):
            return True
        if (
            isinstance(candidate, ipaddress.IPv6Network)
            and isinstance(parent, ipaddress.IPv6Network)
            and candidate.subnet_of(parent)
        ):
            return True
    return False


def _domain_within(value: str, allowed: list[str]) -> bool:
    candidate = _host(value)
    candidate_wildcard = candidate.startswith("*.")
    candidate_base = candidate[2:] if candidate_wildcard else candidate
    for item in allowed:
        rule = _host(item)
        rule_wildcard = rule.startswith("*.")
        rule_base = rule[2:] if rule_wildcard else rule
        if rule_wildcard:
            if candidate_wildcard and (candidate_base == rule_base or candidate_base.endswith("." + rule_base)):
                return True
            if not candidate_wildcard and candidate_base.endswith("." + rule_base):
                return True
        elif candidate_base == rule_base or candidate_base.endswith("." + rule_base):
            return True
    return False


def _port_covered(port: int, ceiling: ScopeContract) -> bool:
    return port in ceiling.allowed_ports or any(item.start <= port <= item.end for item in ceiling.allowed_port_ranges)


def _range_covered(start: int, end: int, ceiling: ScopeContract) -> bool:
    if start == end and _port_covered(start, ceiling):
        return True
    intervals = [(port, port) for port in ceiling.allowed_ports]
    intervals.extend((item.start, item.end) for item in ceiling.allowed_port_ranges)
    cursor = start
    for low, high in sorted(intervals):
        if high < cursor:
            continue
        if low > cursor:
            return False
        cursor = max(cursor, high + 1)
        if cursor > end:
            return True
    return cursor > end


def _require_subset(failures: list[str], name: str, values: Any, ceiling: Any) -> None:
    if not {_policy_value(item) for item in values}.issubset({_policy_value(item) for item in ceiling}):
        failures.append(f"allowed {name} expand the course template")


def _policy_value(value: Any) -> str:
    return str(getattr(value, "value", value)).strip().lower()


__all__ = ["CoursePolicyTemplate", "CoursePolicyRegistry", "CoursePolicyError"]
