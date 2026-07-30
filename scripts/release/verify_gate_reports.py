"""Verify target-environment evidence before an OpenRath GA release."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

GATE_REPORT_FILES = {
    "tests": "tests.json",
    "live_adapters": "live-adapters.json",
    "performance": "performance.json",
    "soak": "soak.json",
    "drills": "drills.json",
    "compatibility": "compatibility.json",
}


def _require_passed(details: dict[str, object], *names: str) -> None:
    failed = sorted(name for name in names if details.get(name) != "passed")
    if failed:
        raise ValueError("required checks did not pass: " + ", ".join(failed))


def _validate_common(
    report: dict[str, object],
    *,
    gate: str,
    source_commit: str,
) -> dict[str, object]:
    if report.get("schema") != "openrath.ga-gate-report/1":
        raise ValueError(f"{gate}: unsupported report schema")
    if report.get("gate") != gate:
        raise ValueError(f"{gate}: gate name does not match the filename")
    if report.get("source_commit") != source_commit:
        raise ValueError(f"{gate}: source_commit does not match the GA candidate")
    if report.get("result") != "passed":
        raise ValueError(f"{gate}: result must be passed")
    generated_at = report.get("generated_at")
    if not isinstance(generated_at, str):
        raise ValueError(f"{gate}: generated_at is required")
    try:
        generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{gate}: generated_at must be ISO 8601") from error
    if generated.tzinfo is None:
        raise ValueError(f"{gate}: generated_at must include a timezone")
    if not isinstance(report.get("environment"), dict):
        raise ValueError(f"{gate}: environment profile is required")
    evidence = report.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(f"{gate}: at least one evidence reference is required")
    if not isinstance(report.get("open_risks"), list):
        raise ValueError(f"{gate}: open_risks must be a list")
    details = report.get("details")
    if not isinstance(details, dict):
        raise ValueError(f"{gate}: details must be an object")
    return details


def _validate_gate(gate: str, details: dict[str, object]) -> None:
    if gate == "tests":
        _require_passed(details, "required_ci")
        if details.get("open_p0") != 0:
            raise ValueError("tests: open_p0 must be zero")
        return
    if gate == "live_adapters":
        _require_passed(details, "provider", "opensandbox", "openviking")
        return
    if gate == "performance":
        _require_passed(details, "single_host", "split_profile")
        efficiency = details.get("worker_scaling_efficiency")
        if (
            isinstance(efficiency, bool)
            or not isinstance(efficiency, (int, float))
            or efficiency < 0.70
        ):
            raise ValueError(
                "performance: worker_scaling_efficiency must be at least 0.70"
            )
        return
    if gate == "soak":
        duration = details.get("duration_seconds")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            raise ValueError("soak: duration_seconds must be numeric")
        if duration < 28800:
            raise ValueError("soak: duration_seconds must be at least 28800")
        if details.get("errors") != 0:
            raise ValueError("soak: errors must be zero")
        if details.get("unexplained_resource_growth") is not False:
            raise ValueError("soak: unexplained_resource_growth must be false")
        return
    if gate == "drills":
        _require_passed(
            details,
            "fault_matrix",
            "backup_restore",
            "rollout_rollback",
        )
        return
    if gate == "compatibility":
        _require_passed(
            details,
            "api_review",
            "v1_maintenance_window",
            "migration",
        )
        return
    raise ValueError(f"unsupported GA gate: {gate}")


def verify_directory(
    directory: Path,
    *,
    source_commit: str,
) -> dict[str, Path]:
    """Verify all Gate C report files and return their paths by gate name."""
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ValueError("source_commit must be 40 lowercase hexadecimal characters")
    validated: dict[str, Path] = {}
    for gate, filename in GATE_REPORT_FILES.items():
        path = directory / filename
        if not path.is_file():
            raise ValueError(f"missing GA gate report: {filename}")
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"{filename}: invalid JSON") from error
        if not isinstance(report, dict):
            raise ValueError(f"{filename}: report must be an object")
        details = _validate_common(
            report,
            gate=gate,
            source_commit=source_commit,
        )
        _validate_gate(gate, details)
        validated[gate] = path
    return validated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    reports = verify_directory(
        args.directory,
        source_commit=args.source_commit,
    )
    print(f"verified {len(reports)} GA gate reports for {args.source_commit}")


if __name__ == "__main__":
    main()
