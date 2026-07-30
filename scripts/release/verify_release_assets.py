"""Verify an existing GitHub Release has the exact expected assets."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_assets(actual_directory: Path, expected_paths: list[Path]) -> None:
    """Reject duplicate names, missing assets, extra assets, or hash mismatches."""
    expected: dict[str, Path] = {}
    for path in expected_paths:
        if not path.is_file():
            raise ValueError(f"expected release asset is missing: {path}")
        if path.name in expected:
            raise ValueError(f"duplicate expected release asset name: {path.name}")
        expected[path.name] = path

    actual = {path.name: path for path in actual_directory.iterdir() if path.is_file()}
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    if missing:
        raise ValueError("GitHub Release is missing assets: " + ", ".join(missing))
    if extra:
        raise ValueError("GitHub Release has unexpected assets: " + ", ".join(extra))
    mismatched = sorted(
        name for name in expected if _sha256(expected[name]) != _sha256(actual[name])
    )
    if mismatched:
        raise ValueError("GitHub Release asset hash mismatch: " + ", ".join(mismatched))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("actual_directory", type=Path)
    parser.add_argument("expected", type=Path, nargs="+")
    args = parser.parse_args()
    try:
        verify_assets(args.actual_directory, args.expected)
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(f"verified {len(args.expected)} existing GitHub Release assets")


if __name__ == "__main__":
    main()
