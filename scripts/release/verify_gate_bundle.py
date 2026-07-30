"""Reject unsafe files and likely credentials before Gate C artifact upload."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ALLOWED_SUFFIXES = frozenset({".csv", ".json", ".log", ".txt", ".xml"})
SENSITIVE_NAMES = frozenset(
    {
        ".env",
        ".pypirc",
        "credentials",
        "credentials.json",
        "kubeconfig",
    }
)
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_BUNDLE_BYTES = 2 * 1024 * 1024 * 1024
SECRET_PATTERNS = (
    re.compile(r"Authorization\s*:\s*Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"pypi-[A-Za-z0-9_-]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"),
    re.compile(
        r"""["']?(?:api[_-]?key|access[_-]?token|secret[_-]?key|password)"""
        r"""["']?\s*[:=]\s*["'][^"'\r\n]{8,}["']""",
        re.IGNORECASE,
    ),
)


def verify_bundle(root: Path) -> dict[str, int]:
    """Return bundle size metadata after validating every file."""
    resolved_root = root.resolve(strict=True)
    if root.is_symlink() or not resolved_root.is_dir():
        raise ValueError("Gate C bundle root must be a real directory")
    files = 0
    total = 0
    for path in resolved_root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Gate C bundle contains a symbolic link: {path}")
        if not path.is_file():
            continue
        if path.name.lower() in SENSITIVE_NAMES:
            raise ValueError(
                f"Gate C bundle contains a sensitive filename: {path.name}"
            )
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            raise ValueError(f"Gate C bundle contains an unsupported extension: {path}")
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise ValueError(f"Gate C evidence file exceeds 50 MiB: {path}")
        total += size
        if total > MAX_BUNDLE_BYTES:
            raise ValueError("Gate C bundle exceeds 2 GiB")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"Gate C evidence must be UTF-8 text: {path}") from error
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                raise ValueError(f"Gate C evidence contains a likely secret: {path}")
        files += 1
    if files == 0:
        raise ValueError("Gate C bundle contains no evidence files")
    return {"files": files, "bytes": total}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    try:
        summary = verify_bundle(args.bundle)
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(
        f"verified Gate C bundle safety: "
        f"{summary['files']} files, {summary['bytes']} bytes"
    )


if __name__ == "__main__":
    main()
