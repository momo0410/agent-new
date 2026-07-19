from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.core.asset_normalizer import AssetInventoryImporter
from app.core.contracts import ScopeContract
from app.routers import api
from app.services.pentest_agent.state import State


def test_imports_single_domain_ip_cidr_and_csv_into_asset_nodes():
    importer = AssetInventoryImporter(ttl_seconds=3600)
    result = importer.import_inventory([
        "192.0.2.10",
        "fixture.example",
        "198.51.100.0/24",
    ], source="fixture")
    node_ids = {node.node_id for node in result.graph.nodes}
    assert {"ip:192.0.2.10", "domain:fixture.example", "cidr:198.51.100.0/24"} <= node_ids
    assert all(node.source_refs and node.expires_at for node in result.graph.nodes)

    csv_result = importer.import_inventory(
        "target,ports,service\nTARGET.example,80;443,https\n",
        source="csv-fixture",
    )
    csv_ids = {node.node_id for node in csv_result.graph.nodes}
    assert {"domain:target.example", "service:target.example|80", "service:target.example|443"} <= csv_ids


def test_inventory_deduplicates_and_preserves_conflicts_and_sources():
    result = AssetInventoryImporter().import_inventory([
        {"target": "HOST.example.", "owner": "team-a"},
        {"target": "host.example", "owner": "team-b"},
    ], source="fixture")
    host = next(node for node in result.graph.nodes if node.node_id == "domain:host.example")
    assert result.deduplicated_count == 1
    assert len(host.source_refs) == 2
    assert host.attributes["owner"] == "team-a"
    assert any(conflict["field"] == "attributes.owner" for conflict in host.conflicts)


def test_inventory_models_aliases_multi_nic_nat_vhosts_services_and_urls():
    result = AssetInventoryImporter().import_assets({
        "assets": [{
            "target": "app.fixture",
            "aliases": ["app-alias.fixture"],
            "interfaces": [{"address": "10.0.0.10", "name": "eth0"}, "10.0.1.10"],
            "external_ip": "203.0.113.10",
            "internal_ip": "10.0.0.10",
            "virtual_hosts": ["tenant.fixture"],
            "services": [{"port": 8443, "service": "https", "score": 80}],
            "urls": ["https://app.fixture:8443/"],
        }],
    }, source="fixture")
    relations = {(edge.source, edge.relation, edge.target) for edge in result.graph.edges}
    assert ("domain:app-alias.fixture", "alias_of", "domain:app.fixture") in relations
    assert ("domain:app.fixture", "has_interface", "ip:10.0.0.10") in relations
    assert ("ip:203.0.113.10", "nat_maps_to", "domain:app.fixture") in relations
    assert ("domain:app.fixture", "nat_maps_to", "ip:10.0.0.10") in relations
    assert ("domain:tenant.fixture", "virtual_host_of", "domain:app.fixture") in relations
    assert "service:app.fixture|8443" in {node.node_id for node in result.graph.nodes}
    assert any(relation == "has_web_site" for _, relation, _ in relations)
    assert result.rejected == []


def test_json_inventory_rejects_bad_service_without_losing_valid_assets():
    result = AssetInventoryImporter().import_data(
        '{"assets":[{"target":"TARGET","services":[{"port":"bad"},{"port":22,"service":"ssh"}]}]}',
        source="json-fixture",
    )
    assert "domain:target" in {node.node_id for node in result.graph.nodes}
    assert "service:target|22" in {node.node_id for node in result.graph.nodes}
    assert result.rejected[0]["reason"] == "invalid_service_port"


def test_asset_import_api_persists_scope_labels_and_idempotent_events(monkeypatch, tmp_path):
    state_path = tmp_path / "pentest_state_asset-api.json"
    state = State(str(state_path))
    scope = ScopeContract(
        owner="fixture-owner",
        allowed_targets=["target.fixture"],
        allowed_cidrs=["10.0.0.0/24"],
        allowed_ports=[443],
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    state.data["scope_contract"] = scope.model_dump(mode="json")
    state.save()
    monkeypatch.setitem(api._pentest_tasks, "asset-api", {"state_file": str(state_path)})
    request = api.AssetInventoryImportRequest(
        task_id="asset-api",
        source="fixture-api",
        inventory={
            "assets": [{
                "target": "target.fixture",
                "aliases": ["outside.fixture"],
                "interfaces": ["10.0.0.9"],
                "public_ip": "203.0.113.9",
                "services": [{"port": 443, "service": "https"}],
            }],
        },
    )
    first = asyncio.run(api.agent_import_assets(request))
    second = asyncio.run(api.agent_import_assets(request))
    assert first["import_id"] == second["import_id"]
    assert first["scope_counts"]["in_scope"] >= 3
    assert first["scope_counts"]["out_of_scope"] >= 2

    reloaded = State(str(state_path))
    assert len(reloaded.data["asset_imports"]) == 1
    graph = reloaded.data["asset_graph"]
    by_id = {node["node_id"]: node for node in graph["nodes"]}
    assert by_id["domain:target.fixture"]["attributes"]["scope_status"] == "IN_SCOPE"
    assert by_id["domain:outside.fixture"]["attributes"]["scope_status"] == "OUT_OF_SCOPE"
    assert by_id["ip:10.0.0.9"]["attributes"]["scope_status"] == "IN_SCOPE"
    events = reloaded.event_store.read()
    assert sum(event.event_type == "asset.inventory.imported" for event in events) == 1
