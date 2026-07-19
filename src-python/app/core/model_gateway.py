"""Unified model gateway with redaction, schema validation and cost accounting."""
from __future__ import annotations

import hashlib
import inspect
import json
import re
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError

from .resource_budget import BudgetExceeded, BudgetManager

T = TypeVar("T")


SECRET_PATTERNS = (
    re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", re.S),
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]+"),
)


class DLPScanner:
    def scan(self, value: str) -> dict[str, Any]:
        findings = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(value)]
        return {"contains_sensitive": bool(findings), "patterns": findings}

    def redact(self, value: str) -> str:
        result = str(value)
        for pattern in SECRET_PATTERNS:
            result = pattern.sub(lambda match: f"{match.group(1) if match.lastindex else 'SENSITIVE'}=[REDACTED]", result)
        return result


@dataclass(frozen=True)
class ModelRoute:
    """Reproducible backend selection metadata for one model request."""

    route_id: str
    strategy: str
    model: str
    model_version: str
    max_output_tokens: int
    reason: str
    task_kind: str
    task_value: float
    complexity: float
    risk: str
    estimated_cost: float = 0.0
    local_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class ModelRouter:
    """Choose deterministic rules, a small model, or a strong model."""

    _RISK_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    _RULE_KINDS = frozenset({
        "classification", "normalization", "deduplication", "redaction",
        "routing", "policy_check", "schema_repair", "status_mapping",
    })

    def __init__(
        self,
        catalog: dict[str, dict[str, Any]] | None = None,
        *,
        rule_max_tokens: int = 256,
        small_max_tokens: int = 1024,
        strong_max_tokens: int = 4096,
        strong_value_threshold: float = 0.75,
        strong_complexity_threshold: float = 0.70,
    ) -> None:
        defaults: dict[str, dict[str, Any]] = {
            "rule": {
                "model": "deterministic-rules",
                "version": "rules.v1",
                "max_output_tokens": rule_max_tokens,
                "cost_per_1k": 0.0,
                "local_only": True,
            },
            "small": {
                "model": "local-small",
                "version": "small.v1",
                "max_output_tokens": small_max_tokens,
                "cost_per_1k": 0.001,
                "local_only": True,
            },
            "strong": {
                "model": "local-strong",
                "version": "strong.v1",
                "max_output_tokens": strong_max_tokens,
                "cost_per_1k": 0.01,
                "local_only": True,
            },
        }
        for key, value in (catalog or {}).items():
            if key in defaults and isinstance(value, dict):
                defaults[key].update(value)
        self.catalog = defaults
        self.strong_value_threshold = max(0.0, min(1.0, float(strong_value_threshold)))
        self.strong_complexity_threshold = max(0.0, min(1.0, float(strong_complexity_threshold)))

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def choose(
        self,
        *,
        task_kind: str = "classification",
        task_value: float = 0.5,
        complexity: float = 0.5,
        risk: str = "low",
        remaining_tokens: int | None = None,
        rules_available: bool = True,
    ) -> ModelRoute:
        kind = str(task_kind or "classification").strip().lower()
        value = self._clamp(task_value)
        complexity_value = self._clamp(complexity)
        risk_value = str(risk or "low").strip().lower()
        risk_rank = self._RISK_RANK.get(risk_value, self._RISK_RANK["medium"])
        if rules_available and kind in self._RULE_KINDS and value <= 0.55 and complexity_value <= 0.45 and risk_rank <= 1:
            strategy = "rule"
            reason = "低价值、低复杂度任务命中确定性规则"
        elif (
            value >= self.strong_value_threshold
            or complexity_value >= self.strong_complexity_threshold
            or risk_rank >= 2
            or kind in {"planning", "reflection", "multi_step_reasoning"}
        ):
            strategy = "strong"
            reason = "高价值或高复杂度任务需要更强规划能力"
        else:
            strategy = "small"
            reason = "常规任务使用小模型控制成本"

        config = self.catalog[strategy]
        max_tokens = max(1, int(config.get("max_output_tokens", 1)))
        if remaining_tokens is not None:
            budget = int(remaining_tokens)
            if budget <= 0:
                raise BudgetExceeded("model route token budget exhausted")
            max_tokens = min(max_tokens, budget)
        route_key = json.dumps(
            {
                "strategy": strategy,
                "model": str(config.get("model", strategy)),
                "version": str(config.get("version", "0")),
                "kind": kind,
                "value": round(value, 4),
                "complexity": round(complexity_value, 4),
                "risk": risk_value,
                "max_tokens": max_tokens,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        route_id = "route_" + hashlib.sha256(route_key.encode("utf-8")).hexdigest()[:20]
        cost = round(max_tokens / 1000 * float(config.get("cost_per_1k", 0.0) or 0.0), 6)
        return ModelRoute(
            route_id=route_id,
            strategy=strategy,
            model=str(config.get("model", strategy)),
            model_version=str(config.get("version", "0")),
            max_output_tokens=max_tokens,
            reason=reason,
            task_kind=kind,
            task_value=value,
            complexity=complexity_value,
            risk=risk_value,
            estimated_cost=cost,
            local_only=bool(config.get("local_only", True)),
        )


@dataclass(frozen=True)
class GatewayCall:
    call_id: str
    model: str
    model_version: str
    template_id: str
    input_hash: str
    output_hash: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    redacted: bool
    status: str
    error: str = ""
    route_id: str = ""
    route_strategy: str = ""
    choice_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class StructuredOutputError(ValueError):
    pass


class ModelGateway:
    def __init__(
        self,
        provider: Callable[..., str | Awaitable[str]],
        *,
        model: str = "local",
        model_version: str = "0",
        budget: BudgetManager | None = None,
        task_id: str = "task",
        dlp: DLPScanner | None = None,
        allow_sensitive_external: bool = False,
        router: ModelRouter | None = None,
        audit_sink: Callable[[dict[str, Any]], Any] | None = None,
    ):
        self.provider = provider
        self.model = model
        self.model_version = model_version
        self.budget = budget
        self.task_id = task_id
        self.dlp = dlp or DLPScanner()
        self.allow_sensitive_external = allow_sensitive_external
        self.router = router
        self.audit_sink = audit_sink
        self.calls: list[GatewayCall] = []

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()

    @staticmethod
    def _estimate_tokens(value: str) -> int:
        return max(1, (len(value) + 3) // 4)

    def route(self, **context: Any) -> ModelRoute | None:
        if self.router is None:
            return None
        return self.router.choose(**context)

    @staticmethod
    def _provider_call(
        provider: Callable[..., str | Awaitable[str]],
        system: str,
        user: str,
        route: ModelRoute | None,
    ) -> str | Awaitable[str]:
        """Keep compatibility with two-argument providers."""
        if route is None:
            return provider(system, user)
        try:
            signature = inspect.signature(provider)
            positional = [
                parameter
                for parameter in signature.parameters.values()
                if parameter.kind
                in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            ]
            accepts_varargs = any(
                parameter.kind == inspect.Parameter.VAR_POSITIONAL
                for parameter in signature.parameters.values()
            )
        except (TypeError, ValueError):
            positional = []
            accepts_varargs = False
        if accepts_varargs or len(positional) >= 3:
            return provider(system, user, route)
        return provider(system, user)

    async def complete(
        self,
        system: str,
        user: str,
        *,
        template_id: str = "default",
        route: ModelRoute | None = None,
        routing_context: dict[str, Any] | None = None,
    ) -> str:
        if route is None and self.router is not None:
            route = self.router.choose(**(routing_context or {}))
        source = f"{system}\n{user}"
        scan = self.dlp.scan(source)
        if scan["contains_sensitive"] and not self.allow_sensitive_external:
            system = self.dlp.redact(system)
            user = self.dlp.redact(user)
        input_text = f"{system}\n{user}"
        input_tokens = self._estimate_tokens(input_text)
        reserved_tokens = input_tokens + (route.max_output_tokens if route else 0)
        if self.budget:
            try:
                self.budget.reserve(self.task_id, llm_tokens=reserved_tokens)
            except BudgetExceeded:
                self._record(
                    template_id,
                    input_text,
                    "",
                    0.0,
                    input_tokens,
                    0,
                    False,
                    "budget_exhausted",
                    "LLM token budget exhausted",
                    route=route,
                )
                raise
        started = time.monotonic()
        try:
            result = self._provider_call(self.provider, system, user, route)
            if hasattr(result, "__await__"):
                result = await result  # type: ignore[assignment]
            output = str(result)
            self._record(
                template_id,
                input_text,
                output,
                (time.monotonic() - started) * 1000,
                input_tokens,
                self._estimate_tokens(output),
                bool(scan["contains_sensitive"]),
                "ok",
                "",
                route=route,
            )
            return output
        except Exception as exc:
            self._record(
                template_id,
                input_text,
                "",
                (time.monotonic() - started) * 1000,
                input_tokens,
                0,
                bool(scan["contains_sensitive"]),
                "error",
                type(exc).__name__,
                route=route,
            )
            raise

    async def complete_json(
        self,
        system: str,
        user: str,
        schema: type[T] | dict[str, Any],
        *,
        template_id: str = "default",
        route: ModelRoute | None = None,
        routing_context: dict[str, Any] | None = None,
    ) -> T:
        text = await self.complete(
            system,
            user,
            template_id=template_id,
            route=route,
            routing_context=routing_context,
        )
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise StructuredOutputError("model output is not valid JSON") from exc
        try:
            if isinstance(schema, type) and issubclass(schema, BaseModel):
                return schema.model_validate(payload)  # type: ignore[return-value]
            return TypeAdapter(schema).validate_python(payload)  # type: ignore[arg-type,return-value]
        except ValidationError as exc:
            raise StructuredOutputError("model output failed schema validation") from exc

    def _record(
        self,
        template_id: str,
        input_text: str,
        output: str,
        latency_ms: float,
        input_tokens: int,
        output_tokens: int,
        redacted: bool,
        status: str,
        error: str,
        *,
        route: ModelRoute | None = None,
    ) -> None:
        call = GatewayCall(
            call_id=f"model_{len(self.calls) + 1}",
            model=route.model if route else self.model,
            model_version=route.model_version if route else self.model_version,
            template_id=template_id,
            input_hash=self._hash(input_text),
            output_hash=self._hash(output),
            latency_ms=round(latency_ms, 3),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=round((input_tokens + output_tokens) / 1000, 6),
            redacted=redacted,
            status=status,
            error=error,
            route_id=route.route_id if route else "",
            route_strategy=route.strategy if route else "",
            choice_reason=route.reason if route else "",
        )
        self.calls.append(call)
        if self.audit_sink is not None:
            with suppress(Exception):
                self.audit_sink(call.as_dict())

    def audit_manifest(self) -> list[dict[str, Any]]:
        return [call.as_dict() for call in self.calls]


__all__ = [
    "DLPScanner",
    "GatewayCall",
    "ModelGateway",
    "ModelRoute",
    "ModelRouter",
    "StructuredOutputError",
]
