"""Deterministic asset and attack-surface graph primitives.

The graph is a compact read model that can be rebuilt from a legacy State
snapshot, keeping migration independent from the executor.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

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
    canonical_id: str = ""
    source_refs: list[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)

    def is_fresh(self, *, now: datetime | None = None) -> bool:
        return self.expires_at is None or self.expires_at > (now or datetime.now(timezone.utc))


class AssetEdge(ContractModel):
    source: str = Field(min_length=1, max_length=255)
    relation: str = Field(min_length=1, max_length=80)
    target: str = Field(min_length=1, max_length=255)
    evidence_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)


class AssetGraph(ContractModel):
    schema_version: str = "asset-graph.v1"
    nodes: list[AssetNode] = Field(default_factory=list)
    edges: list[AssetEdge] = Field(default_factory=list)

    def fresh_nodes(self, *, now: datetime | None = None) -> list[AssetNode]:
        return [node for node in self.nodes if node.is_fresh(now=now)]

    def stale_nodes(self, *, now: datetime | None = None) -> list[AssetNode]:
        return [node for node in self.nodes if not node.is_fresh(now=now)]

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> AssetGraph:
        graph = cls()
        for target in state.get("targets", []):
            target_text = str(target).strip()
            if target_text:
                canonical_node = graph.upsert_host(target_text, kind="target")
                # Keep the historical spelling as a read-only migration alias
                # while all new relations continue to use the canonical node.
                legacy_id = f"target:{target_text.rstrip('.') }"
                if legacy_id != canonical_node.node_id:
                    graph.upsert_node(AssetNode(
                        node_id=legacy_id,
                        canonical_id=canonical_node.canonical_id,
                        kind="target_alias",
                        label=target_text,
                        target=canonical_node.target,
                        aliases=[canonical_node.node_id],
                        attributes={"canonical_target": canonical_node.node_id},
                    ))

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
        for credential in state.get("credentials", []):
            if isinstance(credential, dict):
                target = str(credential.get("target") or credential.get("ip") or "unknown")
                graph.upsert_credential(
                    target,
                    str(credential.get("username") or "unknown"),
                    credential_ref=str(credential.get("secret_ref") or ""),
                    confidence=float(credential.get("confidence_score", 0.5) or 0.5),
                )
        for session in state.get("sessions", []):
            if isinstance(session, dict) and session.get("session_id"):
                graph.upsert_session(
                    str(session.get("target") or "unknown"),
                    str(session["session_id"]),
                    verified=bool(session.get("verified")),
                    confidence=float(session.get("confidence", 0.5) or 0.5),
                )
        for evidence in state.get("canonical_evidence", []):
            if isinstance(evidence, dict) and evidence.get("evidence_id"):
                graph.upsert_evidence(
                    str(evidence.get("target") or "unknown"),
                    str(evidence["evidence_id"]),
                    status=str(evidence.get("status", "INCONCLUSIVE")),
                    confidence=float(evidence.get("confidence", 0.0) or 0.0),
                )
        for finding in state.get("canonical_findings", []):
            if isinstance(finding, dict) and finding.get("title"):
                graph.upsert_vulnerability(
                    str(finding.get("target") or "unknown"),
                    str(finding["title"]),
                    evidence_refs=[str(item) for item in finding.get("evidence_ids", [])],
                    severity=str(finding.get("severity", "info")),
                    confidence=0.8,
                )
        for finding in state.get("web_findings", []):
            if not isinstance(finding, dict):
                continue
            url = str(finding.get("url") or "").strip()
            if not url:
                continue
            parts = urlsplit(url)
            target = f"{parts.scheme}://{parts.netloc}" if parts.netloc else url
            status = str(finding.get("status", "POTENTIALLY_VULNERABLE")).upper()
            severity = "high" if status in {"CONFIRMED", "VULNERABLE"} else "medium"
            graph.upsert_vulnerability(
                target,
                str(finding.get("rule_id") or finding.get("category") or "web-rule"),
                evidence_refs=[str(item) for item in finding.get("evidence_refs", [])],
                severity=severity,
                source_ref="web-rule-engine",
                confidence=0.6 if status not in {"CONFIRMED", "VULNERABLE"} else 0.9,
            )
        for site_id, site in (state.get("web_sites", {}) or {}).items():
            if not isinstance(site, dict):
                continue
            site_node = graph.upsert_web_site(
                str(site.get("origin", site_id)),
                virtual_hosts=[str(item) for item in site.get("virtual_hosts", [])],
                confidence=0.7,
            )
            for endpoint_id, endpoint in (site.get("endpoints", {}) or {}).items():
                if isinstance(endpoint, dict):
                    graph.upsert_endpoint(
                        str(endpoint.get("url", endpoint_id)),
                        site_id=site_node.node_id,
                        method=str(endpoint.get("method", "GET")),
                        confidence=0.7,
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
            # Preserve provenance and surface conflicts rather than silently
            # overwriting a newer observation with a weaker one.
            if existing.service and node.service and existing.service.lower() != node.service.lower():
                conflicts = list(existing.conflicts)
                conflicts.append({"field": "service", "old": existing.service, "new": node.service, "at": datetime.now(timezone.utc).isoformat()})
                updates["conflicts"] = conflicts[-20:]
                if node.confidence < existing.confidence:
                    updates.pop("service", None)
            existing_attributes = dict(existing.attributes)
            incoming_attributes = dict(node.attributes)
            merged_attributes = dict(existing_attributes)
            attribute_conflicts = list(updates.get("conflicts", existing.conflicts))
            for key, value in incoming_attributes.items():
                if key not in existing_attributes:
                    merged_attributes[key] = value
                    continue
                if existing_attributes[key] == value:
                    continue
                attribute_conflicts.append({
                    "field": f"attributes.{key}",
                    "old": existing_attributes[key],
                    "new": value,
                    "at": datetime.now(timezone.utc).isoformat(),
                    "source_refs": list(node.source_refs),
                })
                if node.confidence > existing.confidence:
                    merged_attributes[key] = value
            if incoming_attributes:
                updates["attributes"] = merged_attributes
            if attribute_conflicts:
                updates["conflicts"] = attribute_conflicts[-20:]
            updates["source_refs"] = sorted(set(existing.source_refs + node.source_refs))
            updates["aliases"] = sorted(set(existing.aliases + node.aliases))
            updates["confidence"] = max(existing.confidence, node.confidence)
            merged = existing.model_copy(update=updates)
            self.nodes[index] = merged
            return merged
        self.nodes.append(node)
        return node

    def add_edge(self, source: str, relation: str, target: str, evidence_refs: list[str] | None = None, *, source_refs: list[str] | None = None, confidence: float = 0.0, ttl_seconds: int | None = None) -> None:
        edge = AssetEdge(source=source, relation=relation, target=target, evidence_refs=evidence_refs or [], source_refs=source_refs or [], confidence=max(0.0, min(1.0, confidence)), expires_at=(datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)) if ttl_seconds else None)
        for index, existing in enumerate(self.edges):
            if (existing.source, existing.relation, existing.target) == (source, relation, target):
                self.edges[index] = existing.model_copy(update={
                    "evidence_refs": sorted(set(existing.evidence_refs + edge.evidence_refs)),
                    "source_refs": sorted(set(existing.source_refs + edge.source_refs)),
                    "confidence": max(existing.confidence, edge.confidence),
                    "expires_at": edge.expires_at or existing.expires_at,
                })
                return
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
        source_ref: str = "",
        confidence: float = 0.0,
        ttl_seconds: int | None = None,
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
            canonical_id=f"service:{target.lower()}|{port}",
            source_refs=[source_ref] if source_ref else [],
            confidence=max(0.0, min(1.0, confidence)),
            expires_at=(datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)) if ttl_seconds else None,
        ))
        target_node = self.upsert_host(target, kind="target", source_ref=source_ref, confidence=confidence)
        self.add_edge(target_node.node_id, "exposes", node.node_id)
        return node

    @staticmethod
    def _safe_attributes(attributes: dict[str, Any] | None) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in (attributes or {}).items():
            normalized = str(key)
            if any(word in normalized.lower() for word in ("password", "secret", "token", "private_key", "cookie")):
                result[normalized] = "[REDACTED]"
            else:
                result[normalized] = value
        return result

    def upsert_host(
        self,
        target: str,
        *,
        kind: str = "host",
        aliases: list[str] | None = None,
        source_ref: str = "",
        confidence: float = 0.0,
        attributes: dict[str, Any] | None = None,
    ) -> AssetNode:
        canonical = str(target).strip().lower().rstrip(".")
        prefix = "target" if kind == "target" else "host"
        node = AssetNode(
            node_id=f"{prefix}:{canonical}",
            canonical_id=f"{prefix}:{canonical}",
            kind=kind,
            label=canonical,
            target=canonical,
            aliases=sorted(set(str(item).strip().lower().rstrip(".") for item in (aliases or []) if str(item).strip())),
            source_refs=[source_ref] if source_ref else [],
            confidence=max(0.0, min(1.0, confidence)),
            attributes=self._safe_attributes(attributes),
        )
        return self.upsert_node(node)

    def upsert_web_site(
        self,
        origin: str,
        *,
        virtual_hosts: list[str] | None = None,
        source_ref: str = "",
        confidence: float = 0.0,
    ) -> AssetNode:
        parts = urlsplit(str(origin).strip())
        normalized_origin = f"{parts.scheme.lower()}://{parts.netloc.lower()}" if parts.netloc else str(origin).strip().lower()
        node_id = "web-site:" + normalized_origin
        node = AssetNode(
            node_id=node_id,
            canonical_id=node_id,
            kind="web_site",
            label=normalized_origin,
            target=parts.hostname or parts.netloc or normalized_origin,
            port=parts.port or (443 if parts.scheme.lower() == "https" else 80 if parts.scheme else None),
            source_refs=[source_ref] if source_ref else [],
            confidence=max(0.0, min(1.0, confidence)),
            aliases=sorted(set(str(item).lower() for item in (virtual_hosts or []) if str(item))),
        )
        host = self.upsert_host(node.target, kind="host", source_ref=source_ref, confidence=confidence)
        self.upsert_node(node)
        self.add_edge(host.node_id, "hosts", node.node_id, source_refs=[source_ref] if source_ref else [], confidence=confidence)
        return node

    def upsert_endpoint(
        self,
        url: str,
        *,
        site_id: str = "",
        method: str = "GET",
        source_ref: str = "",
        confidence: float = 0.0,
        attributes: dict[str, Any] | None = None,
    ) -> AssetNode:
        normalized = str(url).strip()
        endpoint_id = f"endpoint:{method.upper()}:{normalized}"
        node = AssetNode(
            node_id=endpoint_id,
            canonical_id=endpoint_id.lower(),
            kind="endpoint",
            label=f"{method.upper()} {normalized}",
            target=urlsplit(normalized).hostname or "",
            source_refs=[source_ref] if source_ref else [],
            confidence=max(0.0, min(1.0, confidence)),
            attributes=self._safe_attributes(attributes),
        )
        self.upsert_node(node)
        if site_id:
            self.add_edge(site_id, "exposes", endpoint_id, source_refs=[source_ref] if source_ref else [], confidence=confidence)
        return node

    def upsert_credential(self, target: str, username: str, *, credential_ref: str = "", source_ref: str = "", confidence: float = 0.0) -> AssetNode:
        node_id = f"credential:{str(target).strip().lower()}:{str(username).strip()}"
        node = AssetNode(
            node_id=node_id,
            canonical_id=node_id.lower(),
            kind="credential",
            label=f"{target}:{username}",
            target=str(target).strip(),
            source_refs=[source_ref] if source_ref else [],
            confidence=max(0.0, min(1.0, confidence)),
            attributes={"credential_ref": credential_ref or "stored-runtime-reference"},
        )
        self.upsert_node(node)
        target_node = self.upsert_host(target, kind="target", source_ref=source_ref, confidence=confidence)
        self.add_edge(target_node.node_id, "has_credential", node_id, source_refs=[source_ref] if source_ref else [], confidence=confidence)
        return node

    def upsert_vulnerability(self, target: str, title: str, *, evidence_refs: list[str] | None = None, severity: str = "info", source_ref: str = "", confidence: float = 0.0) -> AssetNode:
        node_id = f"vulnerability:{str(target).strip().lower()}:{str(title).strip().lower()}"
        node = AssetNode(
            node_id=node_id,
            canonical_id=node_id,
            kind="vulnerability",
            label=str(title).strip(),
            target=str(target).strip(),
            status="VULNERABILITY_CONFIRMED" if str(severity).lower() in {"high", "critical"} else "POTENTIALLY_VULNERABLE",
            score={"critical": 100, "high": 85, "medium": 65, "low": 40, "info": 10}.get(str(severity).lower(), 10),
            source_refs=[source_ref] if source_ref else [],
            confidence=max(0.0, min(1.0, confidence)),
            attributes={"severity": str(severity), "evidence_refs": list(evidence_refs or [])},
        )
        self.upsert_node(node)
        target_node = self.upsert_host(target, kind="target", source_ref=source_ref, confidence=confidence)
        self.add_edge(target_node.node_id, "has_vulnerability", node_id, source_refs=[source_ref] if source_ref else [], confidence=confidence)
        for evidence_ref in evidence_refs or []:
            self.add_edge(node_id, "supported_by", str(evidence_ref), evidence_refs=[str(evidence_ref)], confidence=confidence)
        return node

    def upsert_session(self, target: str, session_id: str, *, verified: bool = False, source_ref: str = "", confidence: float = 0.0) -> AssetNode:
        node_id = f"session:{str(session_id).strip()}"
        node = AssetNode(
            node_id=node_id,
            canonical_id=node_id,
            kind="session",
            label=str(session_id).strip(),
            target=str(target).strip(),
            status="IDENTITY_CONFIRMED" if verified else "SESSION_ESTABLISHED",
            source_refs=[source_ref] if source_ref else [],
            confidence=max(0.0, min(1.0, confidence)),
        )
        self.upsert_node(node)
        target_node = self.upsert_host(target, kind="target", source_ref=source_ref, confidence=confidence)
        self.add_edge(target_node.node_id, "owns_session", node_id, source_refs=[source_ref] if source_ref else [], confidence=confidence)
        return node

    def upsert_evidence(self, target: str, evidence_id: str, *, status: str = "INCONCLUSIVE", source_ref: str = "", confidence: float = 0.0) -> AssetNode:
        node_id = f"evidence:{str(evidence_id).strip()}"
        node = AssetNode(
            node_id=node_id,
            canonical_id=node_id,
            kind="evidence",
            label=str(evidence_id).strip(),
            target=str(target).strip(),
            status=str(status).upper(),
            source_refs=[source_ref] if source_ref else [],
            confidence=max(0.0, min(1.0, confidence)),
        )
        self.upsert_node(node)
        target_node = self.upsert_host(target, kind="target", source_ref=source_ref, confidence=confidence)
        self.add_edge(target_node.node_id, "has_evidence", node_id, source_refs=[source_ref] if source_ref else [], confidence=confidence)
        return node

    def must_try_queue(self, *, minimum_score: int = 50) -> list[AssetNode]:
        terminal = {
            "EXHAUSTED", "NOT_APPLICABLE", "VERIFIED", "EXPLOITED", "FAILED",
            "BLOCKED", "BLOCKED_BY_POLICY", "UNREACHABLE", "VULNERABILITY_CONFIRMED",
        }
        return sorted(
            [
                node for node in self.nodes
                if node.kind in {"service", "endpoint", "web_site"}
                and node.score >= minimum_score
                and str(node.status).upper() not in terminal
                and node.is_fresh()
            ],
            key=lambda node: (-node.score, node.node_id),
        )

    def model_dump_json_ready(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
