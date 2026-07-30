"""Create one hash-bound OpenRath GA Gate C report."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GATES = frozenset(
    {
        "tests",
        "live_adapters",
        "performance",
        "soak",
        "drills",
        "compatibility",
    }
)
CONFIRMATION = "record v2.0.0 gate c"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contained_file(root: Path, path: Path) -> tuple[Path, str]:
    resolved_root = root.resolve(strict=True)
    candidate = path if path.is_absolute() else resolved_root / path
    relative = candidate.resolve(strict=True).relative_to(resolved_root)
    cursor = resolved_root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError(f"evidence path must not contain a symlink: {path}")
    if not candidate.is_file():
        raise ValueError(f"evidence path is not a file: {path}")
    return candidate, relative.as_posix()


def build_report(
    *,
    gate: str,
    source_commit: str,
    environment: dict[str, object],
    details: dict[str, object],
    evidence_root: Path,
    evidence_files: list[Path],
    open_risks: list[object],
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a report that binds every evidence file by relative path and hash."""
    if gate not in GATES:
        raise ValueError(f"unsupported GA gate: {gate}")
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ValueError("source_commit must be 40 lowercase hexadecimal characters")
    if not evidence_files:
        raise ValueError("at least one evidence file is required")
    entries: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in evidence_files:
        path, relative = _contained_file(evidence_root, item)
        if relative in seen:
            raise ValueError(f"duplicate evidence path: {relative}")
        seen.add(relative)
        entries.append(
            {
                "path": relative,
                "sha256": _sha256(path),
                "size": path.stat().st_size,
            }
        )
    return {
        "schema": "openrath.ga-gate-report/1",
        "gate": gate,
        "source_commit": source_commit,
        "result": "passed",
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "environment": environment,
        "evidence": entries,
        "open_risks": open_risks,
        "details": details,
    }


def _object(path: Path, *, name: str) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return value


def _array(path: Path, *, name: str) -> list[object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"{name} must contain a JSON array")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", choices=sorted(GATES), required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--details", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--evidence-file", type=Path, action="append", required=True)
    parser.add_argument("--open-risks", type=Path)
    parser.add_argument("--target-like", action="store_true")
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.confirmation != CONFIRMATION:
        raise SystemExit(f'--confirmation must be exactly "{CONFIRMATION}"')
    report = build_report(
        gate=args.gate,
        source_commit=args.source_commit,
        environment={"profile": args.profile, "target_like": args.target_like},
        details=_object(args.details, name="details"),
        evidence_root=args.evidence_root,
        evidence_files=args.evidence_file,
        open_risks=(
            _array(args.open_risks, name="open risks")
            if args.open_risks is not None
            else []
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"recorded {args.gate} Gate C report at {args.output}")


if __name__ == "__main__":
    main()
