from __future__ import annotations

from pathlib import Path

import pytest

from scripts.release.verify_pypi_files import (
    local_distributions,
    verify_remote_files,
)


def _payload(files: dict[str, str]) -> dict[str, object]:
    return {
        "info": {"version": "2.0.0"},
        "urls": [
            {"filename": filename, "digests": {"sha256": digest}}
            for filename, digest in files.items()
        ],
    }


def test_local_distributions_requires_one_wheel_and_sdist(tmp_path: Path) -> None:
    (tmp_path / "openrath-2.0.0.tar.gz").write_bytes(b"sdist")
    (tmp_path / "openrath-2.0.0-py3-none-any.whl").write_bytes(b"wheel")

    files = local_distributions(tmp_path, version="2.0.0")

    assert set(files) == {
        "openrath-2.0.0.tar.gz",
        "openrath-2.0.0-py3-none-any.whl",
    }


def test_pypi_recovery_accepts_absent_partial_or_complete_identical_files() -> None:
    local = {"openrath-2.0.0.tar.gz": "a" * 64, "openrath-2.0.0.whl": "b" * 64}

    assert not verify_remote_files(local, None, version="2.0.0", require_complete=False)
    assert not verify_remote_files(
        local,
        _payload({"openrath-2.0.0.tar.gz": "a" * 64}),
        version="2.0.0",
        require_complete=False,
    )
    assert verify_remote_files(
        local, _payload(local), version="2.0.0", require_complete=True
    )


def test_pypi_recovery_rejects_conflicting_or_unexpected_files() -> None:
    local = {"openrath-2.0.0.tar.gz": "a" * 64}

    with pytest.raises(ValueError, match="hash mismatch"):
        verify_remote_files(
            local,
            _payload({"openrath-2.0.0.tar.gz": "b" * 64}),
            version="2.0.0",
            require_complete=False,
        )
    with pytest.raises(ValueError, match="unexpected files"):
        verify_remote_files(
            local,
            _payload({**local, "openrath-2.0.0.exe": "c" * 64}),
            version="2.0.0",
            require_complete=False,
        )
