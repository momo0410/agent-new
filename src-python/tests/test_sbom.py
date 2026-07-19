from __future__ import annotations

import json
from pathlib import Path

from scripts.generate_sbom import build_sbom


def test_sbom_contains_both_lock_domains() -> None:
    root = Path(__file__).resolve().parents[2]
    document = build_sbom(root)
    assert document["bomFormat"] == "CycloneDX"
    assert document["specVersion"] == "1.5"
    purls = {item["purl"] for item in document["components"]}
    assert any(item.startswith("pkg:pypi/fastapi@") for item in purls)
    assert any(item.startswith("pkg:npm/vue@") for item in purls)
    assert document["metadata"]["properties"]


def test_sbom_is_json_serialisable_and_ordered() -> None:
    root = Path(__file__).resolve().parents[2]
    first = build_sbom(root)
    second = build_sbom(root)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert [item["purl"] for item in first["components"]] == sorted(item["purl"] for item in first["components"])
