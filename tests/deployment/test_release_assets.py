from __future__ import annotations

from pathlib import Path

import pytest

from scripts.release.verify_release_assets import verify_assets


def test_release_assets_require_exact_names_and_hashes(tmp_path: Path) -> None:
    expected_dir = tmp_path / "expected"
    actual_dir = tmp_path / "actual"
    expected_dir.mkdir()
    actual_dir.mkdir()
    expected = expected_dir / "openrath.whl"
    actual = actual_dir / "openrath.whl"
    expected.write_bytes(b"same")
    actual.write_bytes(b"same")

    verify_assets(actual_dir, [expected])

    actual.write_bytes(b"different")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_assets(actual_dir, [expected])


def test_release_assets_reject_extra_and_duplicate_names(tmp_path: Path) -> None:
    actual_dir = tmp_path / "actual"
    actual_dir.mkdir()
    first = tmp_path / "one" / "asset.json"
    second = tmp_path / "two" / "asset.json"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate expected"):
        verify_assets(actual_dir, [first, second])

    (actual_dir / "extra.json").write_text("extra", encoding="utf-8")
    with pytest.raises(ValueError, match="missing assets"):
        verify_assets(actual_dir, [first])
