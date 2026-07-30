"""Build the OpenRath GA soak gate from target load and resource evidence."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .record_gate import build_report as build_gate_report
except ImportError:  # pragma: no cover - direct script execution
    from record_gate import build_report as build_gate_report


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"evidence must be a JSON object: {path}")
    return value


def _same_commit(source_commit: object, *values: dict[str, Any]) -> str:
    if not isinstance(source_commit, str):
        raise ValueError("soak sample source_commit is missing")
    if any(value.get("source_commit") != source_commit for value in values):
        raise ValueError("all soak evidence must use the same source commit")
    return source_commit


def build_report(
    *,
    sample_path: Path,
    before_snapshot_path: Path,
    after_snapshot_path: Path,
    assessment_path: Path,
    evidence_root: Path,
    environment_profile: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Require an eight-hour error-free target run and an explained resource delta."""
    sample = _object(sample_path)
    before = _object(before_snapshot_path)
    after = _object(after_snapshot_path)
    assessment = _object(assessment_path)
    if sample.get("schema") != "openrath.v2.load-sample/1":
        raise ValueError("unsupported soak load sample schema")
    if sample.get("target_like") is not True or sample.get("profile") != "split":
        raise ValueError("soak sample must use the target-like split profile")
    source_commit = _same_commit(
        sample.get("source_commit"),
        before,
        after,
        assessment,
    )
    snapshot_components: list[set[str]] = []
    for snapshot, phase in ((before, "before"), (after, "after")):
        if snapshot.get("schema") != "openrath.v2.resource-snapshot/1":
            raise ValueError(f"unsupported {phase} resource snapshot schema")
        if snapshot.get("phase") != phase:
            raise ValueError(f"resource snapshot phase must be {phase}")
        components = snapshot.get("components")
        if not isinstance(components, dict) or not components:
            raise ValueError(f"{phase} resource snapshot requires components")
        if any(not isinstance(value, dict) for value in components.values()):
            raise ValueError(f"{phase} resource snapshot components must be objects")
        snapshot_components.append(set(components))
    if snapshot_components[0] != snapshot_components[1]:
        raise ValueError("resource snapshots must contain the same components")
    if assessment.get("schema") != "openrath.v2.resource-assessment/1":
        raise ValueError("unsupported resource assessment schema")
    if (
        not isinstance(assessment.get("assessor"), str)
        or not assessment["assessor"]
        or not isinstance(assessment.get("rationale"), str)
        or not assessment["rationale"]
    ):
        raise ValueError("resource assessment requires an assessor and rationale")
    if assessment.get("unexplained_resource_growth") is not False:
        raise ValueError("soak evidence contains unexplained resource growth")
    duration = sample.get("duration_seconds")
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or duration < 28800
    ):
        raise ValueError("soak duration_seconds must be at least 28800")
    if sample.get("errors") != 0:
        raise ValueError("soak sample must contain zero errors")

    details: dict[str, object] = {
        "duration_seconds": duration,
        "errors": 0,
        "unexplained_resource_growth": False,
        "completed_runs": sample.get("completed_runs"),
        "resource_assessor": assessment["assessor"],
        "resource_rationale": assessment["rationale"],
    }
    return build_gate_report(
        gate="soak",
        source_commit=source_commit,
        environment={"profile": environment_profile, "target_like": True},
        details=details,
        evidence_root=evidence_root,
        evidence_files=[
            sample_path,
            before_snapshot_path,
            after_snapshot_path,
            assessment_path,
        ],
        open_risks=[],
        generated_at=generated_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--before-snapshot", type=Path, required=True)
    parser.add_argument("--after-snapshot", type=Path, required=True)
    parser.add_argument("--assessment", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--environment-profile", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_report(
            sample_path=args.sample,
            before_snapshot_path=args.before_snapshot,
            after_snapshot_path=args.after_snapshot,
            assessment_path=args.assessment,
            evidence_root=args.evidence_root,
            environment_profile=args.environment_profile,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"recorded soak Gate C report at {args.output}")


if __name__ == "__main__":
    main()
