"""Deterministic asset and attack-surface graph primitives.

The graph is a compact read model that can be rebuilt from a legacy State
snapshot, keeping migration independent from the executor.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .contracts import ContractModel


class AssetNode(ContractModel):
    node_id: str = Field(min_length=1, max_length=255)
    kind: str = Field(min_length=1, max_length=40)
    label: str = Field(default="", max_length=240)
    target: str = Field(default="", max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    service: str = Field(default="", max_length=120)
    status: str = Field(default="DISCOVERED", max_length=40)
    score: int = Field(default=0, ge=0, le=100)
    attributes: dict[str, Any] = Field(default_factory=dict)


class AssetEdge(ContractModel):
    source: str = Field(min_length=1, max_length=255)
    relation: str = Field(min_length=1, max_length=80)
    target: str = Field(min_length=1, max_length=255)
    evidence_refs: list[str] = Field(default_factory=list)


class AssetGraph(ContractModel):
    schema_version: str = "asset-graph.v1"
    nodes: list[AssetNode] = Field(default_factory=list)
    edges: list[AssetEdge] = Field(default_factory=list)

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> AssetGraph:
        graph = cls()
        for target in state.get("targets", []):
            target_text = str(target).strip()
            if target_text:
                graph.upsert_node(AssetNode(node_id=f"target:{target_text}", kind="target", label=target_text, target=target_text))

        for finding in state.get("findings", []):
            if not isinstance(finding, dict):
                continue
            target = str(finding.get("ip") or finding.get("target") or "").strip()
            port = finding.get("port")
            try:
                port = int(port) if port is not None else None
            except (TypeError, ValueError):
                port = None
            if target and port:
                graph.upsert_service(target, port, str(finding.get("service") or ""), finding)

        for surface in state.get("attack_surfaces", []):
            if not isinstance(surface, dict):
                continue
            surface_id = str(surface.get("surface_id") or "").strip()
            target, separator, port_text = surface_id.rpartition("|")
            if separator and port_text.isdigit():
                graph.upsert_service(
                    target,
                    int(port_text),
                    str(surface.get("last_tool") or surface.get("purpose") or ""),
                    surface,
                    status=str(surface.get("status") or "DISCOVERED"),
                    score=int(surface.get("score") or 0),
                )
        return graph

    def upsert_node(self, node: AssetNode) -> AssetNode:
        for index, existing in enumerate(self.nodes):
            if existing.node_id != node.node_id:
                continue
            updates = {
                key: value
                for key, value in node.model_dump().items()
                if value not in (None, "", [], {})
            }
            merged = existing.model_copy(update=updates)
            self.nodes[index] = merged
            return merged
        self.nodes.append(node)
        return node

    def add_edge(self, source: str, relation: str, target: str, evidence_refs: list[str] | None = None) -> None:
        edge = AssetEdge(source=source, relation=relation, target=target, evidence_refs=evidence_refs or [])
        if edge not in self.edges:
            self.edges.append(edge)

    def upsert_service(
        self,
        target: str,
        port: int,
        service: str = "",
        attributes: dict[str, Any] | None = None,
        *,
        status: str = "DISCOVERED",
        score: int = 0,
    ) -> AssetNode:
        target = str(target).strip()
        node = self.upsert_node(AssetNode(
            node_id=f"service:{target}|{port}",
            kind="service",
            label=f"{target}:{port}",
            target=target,
            port=port,
            service=str(service or ""),
            status=str(status or "DISCOVERED").upper(),
            score=max(0, min(100, int(score or 0))),
            attributes=attributes or {},
        ))
        self.add_edge(f"target:{target}", "exposes", node.node_id)
        return node

    def must_try_queue(self, *, minimum_score: int = 50) -> list[AssetNode]:
        terminal = {"EXHAUSTED", "NOT_APPLICABLE", "VERIFIED", "EXPLOITED"}
        return sorted(
            [
                node for node in self.nodes
                if node.kind == "service" and node.score >= minimum_score and node.status not in terminal
            ],
            key=lambda node: (-node.score, node.node_id),
        )

    def model_dump_json_ready(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
