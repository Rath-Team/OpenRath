from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.release import verify_gate_reports

SOURCE_COMMIT = "b" * 40


def _reports() -> dict[str, dict[str, object]]:
    common = {
        "schema": "openrath.ga-gate-report/1",
        "source_commit": SOURCE_COMMIT,
        "result": "passed",
        "generated_at": "2026-07-30T12:00:00+00:00",
        "environment": {"profile": "target-like"},
        "evidence": ["artifact://report"],
        "open_risks": [],
    }
    return {
        "tests": {
            **common,
            "gate": "tests",
            "details": {"required_ci": "passed", "open_p0": 0},
        },
        "live_adapters": {
            **common,
            "gate": "live_adapters",
            "details": {
                "provider": "passed",
                "opensandbox": "passed",
                "openviking": "passed",
            },
        },
        "performance": {
            **common,
            "gate": "performance",
            "details": {
                "single_host": "passed",
                "split_profile": "passed",
                "worker_scaling_efficiency": 0.72,
            },
        },
        "soak": {
            **common,
            "gate": "soak",
            "details": {
                "duration_seconds": 28800,
                "errors": 0,
                "unexplained_resource_growth": False,
            },
        },
        "drills": {
            **common,
            "gate": "drills",
            "details": {
                "fault_matrix": "passed",
                "backup_restore": "passed",
                "rollout_rollback": "passed",
            },
        },
        "compatibility": {
            **common,
            "gate": "compatibility",
            "details": {
                "api_review": "passed",
                "v1_maintenance_window": "passed",
                "migration": "passed",
            },
        },
    }


def _write_reports(directory: Path, reports: dict[str, dict[str, object]]) -> None:
    for gate, report in reports.items():
        filename = verify_gate_reports.GATE_REPORT_FILES[gate]
        (directory / filename).write_text(json.dumps(report), encoding="utf-8")


def test_complete_ga_gate_report_set_passes(tmp_path: Path) -> None:
    _write_reports(tmp_path, _reports())
    validated = verify_gate_reports.verify_directory(
        tmp_path,
        source_commit=SOURCE_COMMIT,
    )
    assert set(validated) == set(verify_gate_reports.GATE_REPORT_FILES)


def test_soak_shorter_than_eight_hours_is_rejected(tmp_path: Path) -> None:
    reports = _reports()
    soak_details = reports["soak"]["details"]
    assert isinstance(soak_details, dict)
    soak_details["duration_seconds"] = 28799
    _write_reports(tmp_path, reports)

    with pytest.raises(ValueError, match="28800"):
        verify_gate_reports.verify_directory(
            tmp_path,
            source_commit=SOURCE_COMMIT,
        )


def test_report_from_a_different_source_commit_is_rejected(tmp_path: Path) -> None:
    reports = _reports()
    reports["performance"]["source_commit"] = "c" * 40
    _write_reports(tmp_path, reports)

    with pytest.raises(ValueError, match="source_commit"):
        verify_gate_reports.verify_directory(
            tmp_path,
            source_commit=SOURCE_COMMIT,
        )
