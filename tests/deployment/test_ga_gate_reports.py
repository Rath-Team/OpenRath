from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from scripts.release import record_gate, verify_gate_reports

SOURCE_COMMIT = "b" * 40


def _reports() -> dict[str, dict[str, object]]:
    common = {
        "schema": "openrath.ga-gate-report/1",
        "source_commit": SOURCE_COMMIT,
        "result": "passed",
        "generated_at": "2026-07-30T12:00:00+00:00",
        "environment": {"profile": "staging-us-east", "target_like": True},
        "evidence": [],
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
    evidence_directory = directory / "evidence"
    evidence_directory.mkdir()
    for gate, report in reports.items():
        evidence = evidence_directory / f"{gate}.log"
        evidence.write_text(f"{gate} passed\n", encoding="utf-8")
        report["evidence"] = [
            {
                "path": evidence.relative_to(directory).as_posix(),
                "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                "size": evidence.stat().st_size,
            }
        ]
        filename = verify_gate_reports.GATE_REPORT_FILES[gate]
        (directory / filename).write_text(json.dumps(report), encoding="utf-8")


def test_complete_ga_gate_report_set_passes(tmp_path: Path) -> None:
    _write_reports(tmp_path, _reports())
    validated = verify_gate_reports.verify_directory(
        tmp_path,
        source_commit=SOURCE_COMMIT,
    )
    assert set(validated) == set(verify_gate_reports.GATE_REPORT_FILES)


def test_ga_gate_reports_match_the_committed_json_schema(tmp_path: Path) -> None:
    reports = _reports()
    _write_reports(tmp_path, reports)
    schema = json.loads(
        Path("release/evidence/schema/ga-gate-report.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema)
    for report in reports.values():
        validator.validate(report)


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


def test_rehearsal_environment_is_rejected(tmp_path: Path) -> None:
    reports = _reports()
    reports["tests"]["environment"] = {
        "profile": "docker-desktop",
        "target_like": False,
    }
    _write_reports(tmp_path, reports)

    with pytest.raises(ValueError, match="target_like"):
        verify_gate_reports.verify_directory(
            tmp_path,
            source_commit=SOURCE_COMMIT,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"path": "../outside.log"}, "relative"),
        ({"sha256": "0" * 64}, "hash"),
        ({"size": 999}, "size"),
    ],
)
def test_evidence_files_are_contained_and_hash_bound(
    tmp_path: Path,
    mutation: dict[str, object],
    message: str,
) -> None:
    reports = _reports()
    _write_reports(tmp_path, reports)
    report_path = tmp_path / "tests.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["evidence"][0].update(mutation)
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        verify_gate_reports.verify_directory(
            tmp_path,
            source_commit=SOURCE_COMMIT,
        )


def test_symlink_evidence_is_rejected(tmp_path: Path) -> None:
    reports = _reports()
    _write_reports(tmp_path, reports)
    target = tmp_path / "evidence/tests.log"
    link = tmp_path / "evidence/tests-link.log"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    report_path = tmp_path / "tests.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["evidence"][0]["path"] = "evidence/tests-link.log"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="symlink"):
        verify_gate_reports.verify_directory(
            tmp_path,
            source_commit=SOURCE_COMMIT,
        )


def test_report_recorder_hashes_evidence_without_storing_absolute_paths(
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "bundle"
    evidence_root.mkdir()
    log = evidence_root / "logs/live.txt"
    log.parent.mkdir()
    log.write_text("provider lifecycle passed\n", encoding="utf-8")

    report = record_gate.build_report(
        gate="live_adapters",
        source_commit=SOURCE_COMMIT,
        environment={"profile": "staging-us-east", "target_like": True},
        details={
            "provider": "passed",
            "opensandbox": "passed",
            "openviking": "passed",
        },
        evidence_root=evidence_root,
        evidence_files=[log],
        open_risks=[],
        generated_at="2026-07-30T12:00:00+00:00",
    )

    assert report["evidence"] == [
        {
            "path": "logs/live.txt",
            "sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
            "size": log.stat().st_size,
        }
    ]
