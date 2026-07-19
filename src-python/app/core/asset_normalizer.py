"""Normalize heterogeneous tool observations into graph-ready facts."""
from __future__ import annotations

import csv
import hashlib
import io
import ipaddress
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .asset_graph import AssetGraph, AssetNode


@dataclass(frozen=True)
class NormalizedObservation:
    observation_id: str
    kind: str
    canonical_id: str
    value: dict[str, Any]
    source: str
    parser_version: str
    observed_at: datetime
    confidence: float
    ttl_seconds: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "kind": self.kind,
            "canonical_id": self.canonical_id,
            "value": self.value,
            "source": self.source,
            "parser_version": self.parser_version,
            "observed_at": self.observed_at.isoformat(),
            "confidence": self.confidence,
            "ttl_seconds": self.ttl_seconds,
        }


class AssetNormalizer:
    """Canonicalization is deliberately independent of a target fixture."""

    parser_version = "asset-normalizer.v1"

    @staticmethod
    def canonical_host(value: str) -> str:
        text = str(value or "").strip().lower().rstrip(".")
        try:
            return str(ipaddress.ip_address(text))
        except ValueError:
            return text.encode("idna").decode("ascii") if text else ""

    @classmethod
    def normalize(cls, raw: dict[str, Any], *, source: str = "unknown", confidence: float = 0.5, ttl_seconds: int | None = 86400) -> NormalizedObservation:
        kind = str(raw.get("kind", raw.get("type", "observation"))).strip().lower()
        target = cls.canonical_host(str(raw.get("target", raw.get("host", raw.get("ip", "")))))
        port = raw.get("port")
        try:
            port = int(port) if port is not None else None
        except (TypeError, ValueError):
            port = None
        if kind in {"host", "ip", "domain"}:
            canonical = f"host:{target}"
        elif port is not None and target:
            canonical = f"service:{target}|{port}"
            kind = "service"
        else:
            value_text = str(raw.get("value", raw.get("name", ""))).strip().lower()
            canonical = f"{kind}:{target}:{value_text}".rstrip(":")
        encoded = repr((kind, canonical, raw)).encode("utf-8", errors="replace")
        observation_id = "obs_" + hashlib.sha256(encoded).hexdigest()[:24]
        value = dict(raw)
        if target:
            value["target"] = target
        if port is not None:
            value["port"] = port
        return NormalizedObservation(observation_id, kind, canonical, value, str(source), cls.parser_version, datetime.now(timezone.utc), max(0.0, min(1.0, confidence)), ttl_seconds)

    @classmethod
    def ingest(cls, graph: AssetGraph, observation: NormalizedObservation) -> AssetNode:
        value = observation.value
        target = cls.canonical_host(str(value.get("target", "")))
        port = value.get("port")
        if observation.kind == "service" and target and port:
            return graph.upsert_service(
                target,
                int(port),
                str(value.get("service", value.get("protocol", ""))),
                value,
                status=str(value.get("status", "ENUMERATED")),
                score=int(value.get("score", 0) or 0),
                source_ref=observation.observation_id,
                confidence=observation.confidence,
                ttl_seconds=observation.ttl_seconds,
            )
        node = AssetNode(
            node_id=observation.canonical_id,
            canonical_id=observation.canonical_id,
            kind=observation.kind,
            label=str(value.get("label", target or observation.canonical_id)),
            target=target,
            attributes=value,
            source_refs=[observation.observation_id],
            confidence=observation.confidence,
            expires_at=(observation.observed_at + __import__("datetime").timedelta(seconds=observation.ttl_seconds)) if observation.ttl_seconds else None,
        )
        return graph.upsert_node(node)


@dataclass
class AssetImportResult:
    graph: AssetGraph
    source_records: int
    imported_nodes: list[str]
    observation_ids: list[str]
    deduplicated_count: int
    rejected: list[dict[str, Any]]

    @property
    def imported_edges(self) -> int:
        return len(self.graph.edges)

    @property
    def conflicts(self) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        for node in self.graph.nodes:
            conflicts.extend(node.conflicts)
        for edge in self.graph.edges:
            conflicts.extend(edge.conflicts)
        return conflicts

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "asset-import.v1",
            "source_records": self.source_records,
            "imported_nodes": list(self.imported_nodes),
            "imported_edges": self.imported_edges,
            "observation_ids": list(self.observation_ids),
            "deduplicated_count": self.deduplicated_count,
            "rejected": list(self.rejected),
            "conflicts": self.conflicts,
            "graph": self.graph.model_dump(mode="json"),
        }


class AssetInventoryImporter:
    """Import single targets, CIDRs, JSON/CSV inventories, aliases and NAT maps."""

    schema_version = "asset-import.v1"

    def __init__(self, *, ttl_seconds: int | None = 86400, confidence: float = 0.8):
        self.ttl_seconds = ttl_seconds
        self.confidence = max(0.0, min(1.0, float(confidence)))

    @staticmethod
    def _read_payload(payload: Any) -> Any:
        if isinstance(payload, Path):
            return payload.read_text(encoding="utf-8-sig")
        if not isinstance(payload, str):
            return payload
        text = payload.strip()
        if "\n" not in text and len(text) < 1024:
            try:
                candidate = Path(text)
                if candidate.is_file():
                    return candidate.read_text(encoding="utf-8-sig")
            except OSError:
                # Target-like values may be invalid local path spellings.
                # Preserve them as inventory data instead of path inputs.
                pass
        return text

    @classmethod
    def parse(cls, payload: Any) -> list[dict[str, Any]]:
        payload = cls._read_payload(payload)
        if isinstance(payload, dict):
            for key in ("assets", "inventory", "items", "hosts"):
                nested = payload.get(key)
                if isinstance(nested, list):
                    defaults = {k: v for k, v in payload.items() if k != key}
                    return [
                        {**defaults, **(item if isinstance(item, dict) else {"target": item})}
                        for item in nested
                    ]
            return [dict(payload)]
        if isinstance(payload, (list, tuple, set)):
            return [item if isinstance(item, dict) else {"target": item} for item in payload]
        text = str(payload or "").strip()
        if not text:
            return []
        if text[0] in "[{":
            try:
                return cls.parse(json.loads(text))
            except json.JSONDecodeError:
                pass
        first_line = text.splitlines()[0]
        if "," in first_line and any(
            name in first_line.lower()
            for name in ("target", "host", "ip", "domain", "cidr", "address")
        ):
            return [dict(row) for row in csv.DictReader(io.StringIO(text))]
        return [{"target": line.strip()} for line in text.splitlines() if line.strip()]

    @staticmethod
    def _list(value: Any) -> list[Any]:
        if value in (None, ""):
            return []
        if isinstance(value, (list, tuple, set)):
            return list(value)
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                try:
                    loaded = json.loads(stripped)
                    return loaded if isinstance(loaded, list) else [loaded]
                except json.JSONDecodeError:
                    pass
            return [item.strip() for item in stripped.replace(";", ",").split(",") if item.strip()]
        return [value]

    @staticmethod
    def _primary(row: dict[str, Any]) -> str:
        for key in ("target", "host", "hostname", "ip", "domain", "address", "cidr", "network"):
            value = row.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return ""

    @staticmethod
    def _kind(value: str, requested: str = "") -> tuple[str, str]:
        text = str(value).strip()
        try:
            network = ipaddress.ip_network(text, strict=False)
            if "/" in text:
                return "cidr", network.with_prefixlen
            return "ip", str(network.network_address)
        except ValueError:
            pass
        canonical = AssetNormalizer.canonical_host(text)
        kind = str(requested or "").strip().lower()
        if kind not in {"domain", "host", "hostname", "ip"}:
            kind = "domain" if any(character.isalpha() for character in canonical) else "host"
        if kind == "hostname":
            kind = "host"
        return kind, canonical

    def _node(
        self,
        value: str,
        *,
        row: dict[str, Any],
        graph: AssetGraph,
        source_ref: str,
        aliases: list[str] | None = None,
        kind_hint: str = "",
    ) -> AssetNode:
        kind, canonical = self._kind(value, kind_hint)
        expires_at = (
            datetime.now(timezone.utc) + __import__("datetime").timedelta(seconds=self.ttl_seconds)
            if self.ttl_seconds
            else None
        )
        safe_attributes = graph._safe_attributes({
            key: item
            for key, item in row.items()
            if key not in {"password", "secret", "token", "api_key", "private_key"}
        })
        node_id = f"{kind}:{canonical}"
        return graph.upsert_node(AssetNode(
            node_id=node_id,
            canonical_id=node_id,
            kind=kind,
            label=str(row.get("name") or row.get("label") or canonical),
            target=canonical,
            aliases=sorted(set(AssetNormalizer.canonical_host(str(item)) for item in (aliases or []) if str(item).strip())),
            source_refs=[source_ref],
            confidence=self.confidence,
            expires_at=expires_at,
            attributes=safe_attributes,
        ))

    @staticmethod
    def _services(row: dict[str, Any]) -> list[dict[str, Any]]:
        raw_services = row.get("services")
        if isinstance(raw_services, str) and raw_services.strip().startswith("["):
            try:
                raw_services = json.loads(raw_services)
            except json.JSONDecodeError:
                raw_services = None
        services: list[dict[str, Any]] = []
        if isinstance(raw_services, list):
            for service in raw_services:
                if isinstance(service, dict):
                    services.append(dict(service))
                elif str(service).isdigit():
                    services.append({"port": int(service)})
        ports = AssetInventoryImporter._list(row.get("ports", row.get("port")))
        service_name = str(row.get("service", ""))
        for port in ports:
            if isinstance(port, dict):
                services.append(dict(port))
            elif str(port).strip().isdigit():
                services.append({"port": int(str(port).strip()), "service": service_name})
        return services

    def import_inventory(
        self,
        payload: Any,
        *,
        graph: AssetGraph | None = None,
        source: str = "inventory",
    ) -> AssetImportResult:
        graph = graph or AssetGraph()
        rows = self.parse(payload)
        imported: list[str] = []
        observation_ids: list[str] = []
        rejected: list[dict[str, Any]] = []
        seen: set[str] = set()
        duplicates = 0
        for index, raw_row in enumerate(rows):
            row = dict(raw_row)
            primary = self._primary(row)
            if not primary:
                rejected.append({"index": index, "reason": "missing_target"})
                continue
            source_hash = hashlib.sha256(
                json.dumps(row, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()[:20]
            source_ref = f"asset-import:{source}:{source_hash}"
            observation_ids.append("obs_" + source_hash)
            aliases = [str(item) for item in self._list(row.get("aliases", row.get("alias")))]
            primary_node = self._node(
                primary,
                row=row,
                graph=graph,
                source_ref=source_ref,
                aliases=aliases,
                kind_hint=str(row.get("kind", row.get("type", ""))),
            )
            if primary_node.canonical_id in seen:
                duplicates += 1
            seen.add(primary_node.canonical_id)
            imported.append(primary_node.node_id)

            relation_root = primary_node.node_id
            for alias in aliases:
                alias_node = self._node(alias, row={"label": alias}, graph=graph, source_ref=source_ref)
                graph.add_edge(alias_node.node_id, "alias_of", relation_root, source_refs=[source_ref], confidence=self.confidence, ttl_seconds=self.ttl_seconds)
                imported.append(alias_node.node_id)

            interfaces = self._list(row.get("interfaces", row.get("ips", row.get("addresses"))))
            for interface in interfaces:
                if isinstance(interface, dict):
                    address = str(interface.get("ip") or interface.get("address") or "")
                    interface_row = interface
                else:
                    address = str(interface)
                    interface_row = {"address": address}
                if not address:
                    continue
                interface_node = self._node(address, row=interface_row, graph=graph, source_ref=source_ref, kind_hint="ip")
                graph.add_edge(relation_root, "has_interface", interface_node.node_id, source_refs=[source_ref], confidence=self.confidence, ttl_seconds=self.ttl_seconds)
                imported.append(interface_node.node_id)

            external_values = self._list(row.get("external_ips", row.get("external_ip", row.get("public_ip"))))
            internal_values = self._list(row.get("internal_ips", row.get("internal_ip", row.get("private_ip"))))
            for external in external_values:
                external_node = self._node(str(external), row={"nat_role": "external"}, graph=graph, source_ref=source_ref, kind_hint="ip")
                graph.add_edge(external_node.node_id, "nat_maps_to", relation_root, source_refs=[source_ref], confidence=self.confidence, ttl_seconds=self.ttl_seconds)
                imported.append(external_node.node_id)
            for internal in internal_values:
                internal_node = self._node(str(internal), row={"nat_role": "internal"}, graph=graph, source_ref=source_ref, kind_hint="ip")
                graph.add_edge(relation_root, "nat_maps_to", internal_node.node_id, source_refs=[source_ref], confidence=self.confidence, ttl_seconds=self.ttl_seconds)
                imported.append(internal_node.node_id)

            for virtual_host in self._list(row.get("virtual_hosts", row.get("vhosts"))):
                vhost_node = self._node(str(virtual_host), row={"virtual_host": True}, graph=graph, source_ref=source_ref, kind_hint="domain")
                graph.add_edge(vhost_node.node_id, "virtual_host_of", relation_root, source_refs=[source_ref], confidence=self.confidence, ttl_seconds=self.ttl_seconds)
                imported.append(vhost_node.node_id)

            service_target = primary_node.target
            for service in self._services(row):
                try:
                    port = int(service.get("port"))
                except (TypeError, ValueError):
                    rejected.append({"index": index, "reason": "invalid_service_port", "value": service.get("port")})
                    continue
                if not 1 <= port <= 65535:
                    rejected.append({"index": index, "reason": "invalid_service_port", "value": port})
                    continue
                service_node = graph.upsert_service(
                    service_target,
                    port,
                    str(service.get("service") or service.get("name") or service.get("protocol") or ""),
                    service,
                    status=str(service.get("status", "DISCOVERED")),
                    score=int(service.get("score", 0) or 0),
                    source_ref=source_ref,
                    confidence=self.confidence,
                    ttl_seconds=self.ttl_seconds,
                )
                imported.append(service_node.node_id)

            for url in self._list(row.get("urls", row.get("url"))):
                site = graph.upsert_web_site(str(url), source_ref=source_ref, confidence=self.confidence)
                graph.add_edge(relation_root, "has_web_site", site.node_id, source_refs=[source_ref], confidence=self.confidence, ttl_seconds=self.ttl_seconds)
                imported.append(site.node_id)

        return AssetImportResult(
            graph=graph,
            source_records=len(rows),
            imported_nodes=list(dict.fromkeys(imported)),
            observation_ids=list(dict.fromkeys(observation_ids)),
            deduplicated_count=duplicates,
            rejected=rejected,
        )

    def import_assets(self, payload: Any, **kwargs: Any) -> AssetImportResult:
        return self.import_inventory(payload, **kwargs)

    def import_data(self, payload: Any, **kwargs: Any) -> AssetImportResult:
        return self.import_inventory(payload, **kwargs)


__all__ = [
    "AssetImportResult",
    "AssetInventoryImporter",
    "AssetNormalizer",
    "NormalizedObservation",
]
