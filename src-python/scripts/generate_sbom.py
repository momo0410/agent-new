"""Generate a deterministic CycloneDX SBOM for the two SDIT dependency locks.

The generator deliberately reads lock files instead of the current interpreter or
``node_modules``.  A release therefore describes the exact inputs that CI verified,
even when the build host has extra packages installed.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any


_PYTHON_REQUIREMENT = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)(?:\s*;\s*(.*?))?\s*(?:\\)?\s*$"
)
_PYTHON_HASH = re.compile(r"--hash=sha256:([0-9a-fA-F]{64})")


def _normalise_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _purl(ecosystem: str, name: str, version: str) -> str:
    return f"pkg:{ecosystem}/{name.replace(' ', '%20')}@{version}"


def _python_components(lock_path: Path) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        match = _PYTHON_REQUIREMENT.match(line)
        if match:
            name, version, marker = match.groups()
            current = {
                "type": "library",
                "group": "python",
                "name": name,
                "version": version,
                "purl": _purl("pypi", name, version),
                "bom-ref": _purl("pypi", name, version),
            }
            if marker:
                current["properties"] = [{"name": "sdit:marker", "value": marker}]
            components.append(current)
            continue
        if current is not None:
            hash_match = _PYTHON_HASH.search(line)
            if hash_match:
                current.setdefault("hashes", []).append(
                    {"alg": "SHA-256", "content": hash_match.group(1).lower()}
                )
    return components


def _integrity_hash(value: str) -> dict[str, str] | None:
    if not value or "-" not in value:
        return None
    algorithm, encoded = value.split("-", 1)
    algorithm = algorithm.upper().replace("SHA", "SHA-") if algorithm.lower().startswith("sha") else algorithm.upper()
    try:
        content = base64.b64decode(encoded).hex()
    except (ValueError, TypeError):
        return None
    return {"alg": algorithm, "content": content}


def _npm_components(lock_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    document = json.loads(lock_path.read_text(encoding="utf-8"))
    packages = document.get("packages", {})
    components: list[dict[str, Any]] = []
    dependencies: list[dict[str, Any]] = []
    refs_by_path: dict[str, str] = {}
    for package_path, metadata in sorted(packages.items()):
        if not package_path or not isinstance(metadata, dict) or not metadata.get("version"):
            continue
        name = str(metadata.get("name") or package_path.removeprefix("node_modules/"))
        version = str(metadata["version"])
        ref = _purl("npm", name, version)
        refs_by_path[package_path] = ref
        component: dict[str, Any] = {
            "type": "library",
            "group": "npm",
            "name": name,
            "version": version,
            "purl": ref,
            "bom-ref": ref,
        }
        integrity = _integrity_hash(str(metadata.get("integrity", "")))
        if integrity:
            component["hashes"] = [integrity]
        if metadata.get("license"):
            component["licenses"] = [{"license": {"id": str(metadata["license"])}}]
        if metadata.get("dev") is True:
            component["scope"] = "optional"
        components.append(component)

    # npm's v3 lock stores dependency edges relative to each package directory.
    for package_path, metadata in sorted(packages.items()):
        parent_ref = refs_by_path.get(package_path)
        if not parent_ref or not isinstance(metadata, dict):
            continue
        for dependency_name in sorted((metadata.get("dependencies") or {}).keys()):
            child_path = f"{package_path}/node_modules/{dependency_name}" if package_path else f"node_modules/{dependency_name}"
            child_ref = refs_by_path.get(child_path)
            if child_ref:
                dependencies.append({"ref": parent_ref, "dependsOn": [child_ref]})
    return components, dependencies


def build_sbom(root: Path) -> dict[str, Any]:
    python_lock = root / "src-python" / "requirements.lock"
    npm_lock = root / "package-lock.json"
    python_components = _python_components(python_lock)
    npm_components, npm_edges = _npm_components(npm_lock)
    components = sorted(
        python_components + npm_components,
        key=lambda item: (str(item.get("purl", "")), str(item.get("version", ""))),
    )
    root_ref = "sdit@" + str(json.loads((root / "package.json").read_text(encoding="utf-8"))["version"])
    dependencies = [{"ref": root_ref, "dependsOn": [item["bom-ref"] for item in components]}]
    dependencies.extend(npm_edges)
    lock_hashes = {
        "python": hashlib.sha256(python_lock.read_bytes()).hexdigest(),
        "npm": hashlib.sha256(npm_lock.read_bytes()).hexdigest(),
    }
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": "urn:uuid:" + hashlib.sha256(json.dumps(lock_hashes, sort_keys=True).encode()).hexdigest()[:32],
        "version": 1,
        "metadata": {
            "timestamp": "2026-07-18T00:00:00Z",
            "tools": [{"vendor": "SDIT", "name": "generate_sbom.py", "version": "1.0.0"}],
            "component": {
                "type": "application",
                "name": "SDIT",
                "version": root_ref.rsplit("@", 1)[-1],
                "bom-ref": root_ref,
            },
            "properties": [
                {"name": "sdit:lock:python:sha256", "value": lock_hashes["python"]},
                {"name": "sdit:lock:npm:sha256", "value": lock_hashes["npm"]},
            ],
        },
        "components": components,
        "dependencies": dependencies,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = build_sbom(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"components": len(document["components"]), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
