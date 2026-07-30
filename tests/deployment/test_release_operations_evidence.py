from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.release import build_drill_report, build_soak_report

SOURCE_COMMIT = "e" * 40


def _write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _soak_sample(*, duration: float = 28800, errors: int = 0) -> dict[str, Any]:
    return {
        "schema": "openrath.v2.load-sample/1",
        "source_commit": SOURCE_COMMIT,
        "profile": "split",
        "target_like": True,
        "worker_replicas": 4,
        "duration_seconds": duration,
        "attempted_runs": 1000,
        "completed_runs": 1000 - errors,
        "errors": errors,
        "throughput_runs_per_second": 3.0,
        "latency_seconds": {"p50": 0.2, "p95": 0.5, "p99": 0.8},
        "generated_at": "2026-07-30T12:00:00Z",
        "target_origin": "https://target.example",
    }


def _snapshot(phase: str, memory: int) -> dict[str, Any]:
    return {
        "schema": "openrath.v2.resource-snapshot/1",
        "source_commit": SOURCE_COMMIT,
        "phase": phase,
        "captured_at": "2026-07-30T12:00:00Z",
        "components": {
            "api": {"memory_bytes": memory, "restarts": 0},
            "worker": {"memory_bytes": memory, "restarts": 0},
        },
    }


def _assessment(*, unexplained: bool = False) -> dict[str, Any]:
    return {
        "schema": "openrath.v2.resource-assessment/1",
        "source_commit": SOURCE_COMMIT,
        "assessor": "operations-owner",
        "unexplained_resource_growth": unexplained,
        "rationale": "Resource use stabilized after warm-up.",
    }


def test_soak_report_binds_eight_hour_run_and_resource_assessment(
    tmp_path: Path,
) -> None:
    sample = _write(tmp_path / "raw/soak.json", _soak_sample())
    before = _write(tmp_path / "raw/before.json", _snapshot("before", 100))
    after = _write(tmp_path / "raw/after.json", _snapshot("after", 110))
    assessment = _write(tmp_path / "raw/assessment.json", _assessment())

    report = build_soak_report.build_report(
        sample_path=sample,
        before_snapshot_path=before,
        after_snapshot_path=after,
        assessment_path=assessment,
        evidence_root=tmp_path,
        environment_profile="staging-us-east",
        generated_at="2026-07-30T21:00:00Z",
    )

    assert report["details"]["duration_seconds"] == 28800
    assert report["details"]["errors"] == 0
    assert report["details"]["unexplained_resource_growth"] is False
    assert len(report["evidence"]) == 4


@pytest.mark.parametrize(
    ("duration", "errors", "unexplained", "message"),
    [
        (28799, 0, False, "28800"),
        (28800, 1, False, "zero errors"),
        (28800, 0, True, "unexplained"),
    ],
)
def test_soak_report_rejects_incomplete_acceptance(
    tmp_path: Path,
    duration: float,
    errors: int,
    unexplained: bool,
    message: str,
) -> None:
    sample = _write(
        tmp_path / "raw/soak.json", _soak_sample(duration=duration, errors=errors)
    )
    before = _write(tmp_path / "raw/before.json", _snapshot("before", 100))
    after = _write(tmp_path / "raw/after.json", _snapshot("after", 110))
    assessment = _write(
        tmp_path / "raw/assessment.json",
        _assessment(unexplained=unexplained),
    )
    with pytest.raises(ValueError, match=message):
        build_soak_report.build_report(
            sample_path=sample,
            before_snapshot_path=before,
            after_snapshot_path=after,
            assessment_path=assessment,
            evidence_root=tmp_path,
            environment_profile="staging-us-east",
        )


def test_soak_report_requires_comparable_resource_components(tmp_path: Path) -> None:
    sample = _write(tmp_path / "raw/soak.json", _soak_sample())
    before = _write(tmp_path / "raw/before.json", _snapshot("before", 100))
    after_value = _snapshot("after", 110)
    del after_value["components"]["worker"]
    after = _write(tmp_path / "raw/after.json", after_value)
    assessment = _write(tmp_path / "raw/assessment.json", _assessment())

    with pytest.raises(ValueError, match="same components"):
        build_soak_report.build_report(
            sample_path=sample,
            before_snapshot_path=before,
            after_snapshot_path=after,
            assessment_path=assessment,
            evidence_root=tmp_path,
            environment_profile="staging-us-east",
        )


def _drill_results() -> dict[str, Any]:
    required = (
        "postgresql_failure",
        "redis_failure",
        "s3_failure",
        "api_failure",
        "worker_failure",
        "backup_restore",
        "rollout_rollback",
    )
    return {
        "schema": "openrath.v2.drill-results/1",
        "source_commit": SOURCE_COMMIT,
        "environment_profile": "staging-us-east",
        "drills": {
            name: {
                "status": "passed",
                "operator": "operations-owner",
                "started_at": "2026-07-30T12:00:00Z",
                "completed_at": "2026-07-30T12:05:00Z",
                "recovery_seconds": 300,
                "data_loss_records": 0,
                "observed": f"{name} recovered",
            }
            for name in required
        },
    }


def test_drill_report_requires_full_fault_restore_and_rollback_matrix(
    tmp_path: Path,
) -> None:
    results = _write(tmp_path / "raw/drills.json", _drill_results())
    log = _write(tmp_path / "raw/operator-log.json", {"events": ["passed"]})

    report = build_drill_report.build_report(
        results_path=results,
        evidence_paths=[log],
        evidence_root=tmp_path,
        generated_at="2026-07-30T14:00:00Z",
    )

    assert report["details"] == {
        "fault_matrix": "passed",
        "backup_restore": "passed",
        "rollout_rollback": "passed",
    }


def test_drill_report_rejects_missing_drill_data_loss_and_rto_breach(
    tmp_path: Path,
) -> None:
    results = _drill_results()
    del results["drills"]["redis_failure"]
    path = _write(tmp_path / "raw/drills.json", results)
    with pytest.raises(ValueError, match="missing drills"):
        build_drill_report.build_report(
            results_path=path,
            evidence_paths=[],
            evidence_root=tmp_path,
        )

    results = _drill_results()
    results["drills"]["worker_failure"]["completed_at"] = "2026-07-30T11:00:00Z"
    path.write_text(json.dumps(results), encoding="utf-8")
    with pytest.raises(ValueError, match="completion"):
        build_drill_report.build_report(
            results_path=path,
            evidence_paths=[],
            evidence_root=tmp_path,
        )

    results = _drill_results()
    results["drills"]["backup_restore"]["data_loss_records"] = 1
    path.write_text(json.dumps(results), encoding="utf-8")
    with pytest.raises(ValueError, match="data loss"):
        build_drill_report.build_report(
            results_path=path,
            evidence_paths=[],
            evidence_root=tmp_path,
        )

    results["drills"]["backup_restore"]["data_loss_records"] = 0
    results["drills"]["backup_restore"]["recovery_seconds"] = 3601
    path.write_text(json.dumps(results), encoding="utf-8")
    with pytest.raises(ValueError, match="3600"):
        build_drill_report.build_report(
            results_path=path,
            evidence_paths=[],
            evidence_root=tmp_path,
        )
