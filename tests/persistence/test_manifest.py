"""P3.3 — root layout manifest (.openrath/manifest.json).

Records the layout version + per-plane schema versions so upgrades are
coordinated and a future/newer layout is detected with a clear error instead
of silent misreads.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rath.persistence.manifest import (
    LAYOUT_VERSION,
    ManifestVersionError,
    check_manifest,
    ensure_manifest,
    read_manifest,
)


def test_ensure_creates_manifest(tmp_path: Path) -> None:
    m = ensure_manifest(tmp_path)
    assert m["layout_version"] == LAYOUT_VERSION
    assert "planes" in m and set(m["planes"]) >= {"config", "backend", "memory"}
    path = tmp_path / "manifest.json"
    assert path.is_file()
    # Parseable, and per-plane schema versions are recorded ints.
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk == m
    assert all(isinstance(v, int) for v in m["planes"].values())


def test_ensure_is_idempotent(tmp_path: Path) -> None:
    first = ensure_manifest(tmp_path)
    second = ensure_manifest(tmp_path)
    assert first == second


def test_read_missing_returns_none(tmp_path: Path) -> None:
    assert read_manifest(tmp_path) is None


def test_check_detects_newer_layout(tmp_path: Path) -> None:
    ensure_manifest(tmp_path)
    # Simulate a manifest written by a newer OpenRath.
    path = tmp_path / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["layout_version"] = LAYOUT_VERSION + 1
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ManifestVersionError, match="newer"):
        check_manifest(tmp_path)


def test_check_passes_for_current(tmp_path: Path) -> None:
    ensure_manifest(tmp_path)
    # Should not raise.
    check_manifest(tmp_path)


def test_check_noop_when_absent(tmp_path: Path) -> None:
    # No manifest yet (fresh/legacy root) → check is a no-op, not an error.
    check_manifest(tmp_path)
