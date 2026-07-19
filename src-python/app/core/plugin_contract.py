"""Versioned plugin contract and registry for tool adapters."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import Field

from .contracts import ActionLevel, ContractModel


class PluginManifest(ContractModel):
    plugin_id: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=64)
    description: str = ""
    action_level: ActionLevel
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    evidence_types: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    timeout_seconds: float = Field(default=60.0, gt=0, le=86400)
    supports_cancel: bool = True
    supports_dry_run: bool = True
    supports_simulation: bool = True
    cleanup_actions: list[str] = Field(default_factory=list)
    risk: str = "low"


@dataclass(frozen=True)
class PluginResult:
    plugin_id: str
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    evidence: tuple[dict[str, Any], ...] = ()
    cleanup_required: bool = False
    reason: str = ""


class PluginRegistry:
    def __init__(self):
        self._manifests: dict[str, PluginManifest] = {}
        self._handlers: dict[str, Callable[..., PluginResult]] = {}

    def register(self, manifest: PluginManifest, handler: Callable[..., PluginResult] | None = None) -> None:
        if manifest.plugin_id in self._manifests:
            raise ValueError(f"duplicate plugin: {manifest.plugin_id}")
        self._manifests[manifest.plugin_id] = manifest
        if handler is not None:
            self._handlers[manifest.plugin_id] = handler

    def manifest(self, plugin_id: str) -> PluginManifest | None:
        return self._manifests.get(str(plugin_id))

    def enabled(self, plugin_id: str) -> bool:
        return str(plugin_id) in self._manifests

    def run(self, plugin_id: str, **kwargs: Any) -> PluginResult:
        manifest = self.manifest(plugin_id)
        if manifest is None:
            return PluginResult(str(plugin_id), "denied", reason="plugin is not registered")
        handler = self._handlers.get(plugin_id)
        if handler is None:
            return PluginResult(plugin_id, "unavailable", reason="plugin handler is unavailable")
        try:
            result = handler(**kwargs)
            if not isinstance(result, PluginResult):
                return PluginResult(plugin_id, "failed", reason="handler returned an invalid result")
            return result
        except Exception as exc:
            return PluginResult(plugin_id, "failed", reason=f"plugin error: {type(exc).__name__}", cleanup_required=True)

    def manifests(self) -> list[PluginManifest]:
        return list(self._manifests.values())

    def as_dict(self) -> dict[str, dict[str, Any]]:
        return {key: value.model_dump(mode="json") for key, value in self._manifests.items()}

