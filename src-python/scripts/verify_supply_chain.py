"""Check that release metadata points at the committed dependency inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = root / "docker" / "toolchain.lock.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dockerfile_rel = str(manifest["image"]["dockerfile"])
    dockerfile = root / dockerfile_rel
    if sha256(dockerfile) != manifest["dockerfile_sha256"]:
        errors.append("Dockerfile hash differs from toolchain manifest")
    base = str(manifest["image"]["base"])
    digest = str(manifest["image"]["base_digest"])
    from_line = next((line.strip() for line in dockerfile.read_text(encoding="utf-8").splitlines() if line.startswith("FROM ")), "")
    if f"FROM {base}@{digest}" not in from_line:
        errors.append("Dockerfile base image does not match toolchain manifest")
    for key in ("python", "python_dev", "npm"):
        relative = str(manifest["lockfiles"][key])
        path = root / relative
        expected = str(manifest["lockfiles"][f"{key}_sha256"])
        if sha256(path) != expected:
            errors.append(f"{relative} hash differs from toolchain manifest")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        errors.append("base image digest is not immutable")
    if not re.fullmatch(r"\d{8}T\d{6}Z", str(manifest["image"]["debian_snapshot"])):
        errors.append("Debian snapshot must be an immutable timestamp")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    errors = verify(args.root.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("supply-chain metadata verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
