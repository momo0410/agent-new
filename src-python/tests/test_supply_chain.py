from __future__ import annotations

from pathlib import Path

from scripts.verify_supply_chain import verify


def test_toolchain_manifest_matches_committed_inputs() -> None:
    root = Path(__file__).resolve().parents[2]
    assert verify(root) == []
