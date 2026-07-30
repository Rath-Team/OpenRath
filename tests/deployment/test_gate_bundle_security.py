from __future__ import annotations

from pathlib import Path

import pytest

from scripts.release.verify_gate_bundle import verify_bundle


def test_gate_bundle_allows_only_small_utf8_evidence_files(tmp_path: Path) -> None:
    report = tmp_path / "tests.json"
    report.write_text('{"result":"passed"}', encoding="utf-8")
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    log = evidence / "tests.log"
    log.write_text("1083 tests passed\n", encoding="utf-8")

    summary = verify_bundle(tmp_path)

    assert summary == {
        "files": 2,
        "bytes": report.stat().st_size + log.stat().st_size,
    }


@pytest.mark.parametrize(
    "content",
    [
        "Authorization: Bearer secret-value-that-must-not-leak",
        "pypi-abcdefghijklmnopqrstuvwxyz0123456789",
        "github_pat_abcdefghijklmnopqrstuvwxyz0123456789",
        "-----BEGIN PRIVATE KEY-----",
        '"api_key": "secret-value-that-must-not-leak"',
    ],
)
def test_gate_bundle_rejects_high_confidence_secret_patterns(
    tmp_path: Path,
    content: str,
) -> None:
    (tmp_path / "evidence.log").write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="secret"):
        verify_bundle(tmp_path)


def test_gate_bundle_rejects_unsupported_binary_and_sensitive_names(
    tmp_path: Path,
) -> None:
    (tmp_path / "capture.zip").write_bytes(b"archive")
    with pytest.raises(ValueError, match="extension"):
        verify_bundle(tmp_path)

    (tmp_path / "capture.zip").unlink()
    (tmp_path / ".env").write_text("SAFE=value", encoding="utf-8")
    with pytest.raises(ValueError, match="sensitive"):
        verify_bundle(tmp_path)


def test_gate_bundle_rejects_symbolic_links(tmp_path: Path) -> None:
    target = tmp_path / "target.log"
    target.write_text("safe", encoding="utf-8")
    link = tmp_path / "link.log"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(ValueError, match="symbolic"):
        verify_bundle(tmp_path)
