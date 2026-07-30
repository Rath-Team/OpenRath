"""Build the OpenRath GA drill gate from operator-controlled target exercises."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .record_gate import build_report as build_gate_report
except ImportError:  # pragma: no cover - direct script execution
    from record_gate import build_report as build_gate_report

FAULT_DRILLS = frozenset(
    {
        "postgresql_failure",
        "redis_failure",
        "s3_failure",
        "api_failure",
        "worker_failure",
    }
)
REQUIRED_DRILLS = FAULT_DRILLS | {"backup_restore", "rollout_rollback"}


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"drill results must be a JSON object: {path}")
    return value


def _timestamp(value: object, *, field: str, drill: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"drill {drill} requires {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"drill {drill} has invalid {field}") from error
    if parsed.tzinfo is None:
        raise ValueError(f"drill {drill} {field} requires a timezone")
    return parsed


def _validate_drill(name: str, value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"drill result must be an object: {name}")
    if value.get("status") != "passed":
        raise ValueError(f"drill did not pass: {name}")
    for field in ("operator", "observed"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise ValueError(f"drill {name} requires {field}")
    started = _timestamp(value.get("started_at"), field="started_at", drill=name)
    completed = _timestamp(value.get("completed_at"), field="completed_at", drill=name)
    if completed < started:
        raise ValueError(f"drill {name} completion precedes its start")
    recovery = value.get("recovery_seconds")
    if (
        isinstance(recovery, bool)
        or not isinstance(recovery, (int, float))
        or recovery < 0
    ):
        raise ValueError(f"drill {name} requires non-negative recovery_seconds")
    if value.get("data_loss_records") != 0:
        raise ValueError(f"drill {name} reports data loss")
    if name == "backup_restore" and recovery > 3600:
        raise ValueError("backup_restore recovery_seconds must not exceed 3600")


def build_report(
    *,
    results_path: Path,
    evidence_paths: list[Path],
    evidence_root: Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Validate the complete target drill matrix and bind its logs."""
    results = _object(results_path)
    if results.get("schema") != "openrath.v2.drill-results/1":
        raise ValueError("unsupported drill results schema")
    source_commit = results.get("source_commit")
    if (
        not isinstance(source_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
    ):
        raise ValueError("drill results require a valid source_commit")
    profile = results.get("environment_profile")
    if not isinstance(profile, str) or not profile:
        raise ValueError("drill results require an environment_profile")
    drills = results.get("drills")
    if not isinstance(drills, dict):
        raise ValueError("drill results require a drills object")
    missing = sorted(REQUIRED_DRILLS - set(drills))
    if missing:
        raise ValueError("missing drills: " + ", ".join(missing))
    for name in sorted(REQUIRED_DRILLS):
        _validate_drill(name, drills[name])

    return build_gate_report(
        gate="drills",
        source_commit=source_commit,
        environment={"profile": profile, "target_like": True},
        details={
            "fault_matrix": "passed",
            "backup_restore": "passed",
            "rollout_rollback": "passed",
        },
        evidence_root=evidence_root,
        evidence_files=[results_path, *evidence_paths],
        open_risks=[],
        generated_at=generated_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--evidence-file", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_report(
            results_path=args.results,
            evidence_paths=args.evidence_file,
            evidence_root=args.evidence_root,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"recorded drills Gate C report at {args.output}")


if __name__ == "__main__":
    main()
