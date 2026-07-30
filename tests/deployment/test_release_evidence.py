from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.release import build_evidence, create_ga_approval, verify_evidence

SOURCE_COMMIT = "a" * 40


def _approval() -> dict[str, object]:
    return {
        "schema": "openrath.ga-approval/1",
        "version": "2.0.0",
        "source_commit": SOURCE_COMMIT,
        "approved": True,
        "approved_at": "2026-07-30T12:00:00+00:00",
        "approvers": ["release-owner"],
        "requested_by": "release-requester",
        "environment": "ga-release",
        "environment_reviews": [
            {
                "review_id": "42",
                "reviewer": "release-owner",
                "approved_at": "2026-07-30T12:00:00+00:00",
            }
        ],
        "repository": "Rath-Team/OpenRath",
        "workflow_run_id": "12345",
        "actions": {
            "pypi": True,
            "ghcr": True,
            "github_release": True,
        },
    }


def test_release_stage_is_inferred_from_exact_supported_versions() -> None:
    assert build_evidence.infer_release_stage("2.0.0rc1") == "rc"
    assert build_evidence.infer_release_stage("2.0.0rc12") == "rc"
    assert build_evidence.infer_release_stage("2.0.0") == "ga"

    with pytest.raises(ValueError, match="unsupported release version"):
        build_evidence.infer_release_stage("2.0.1")


def test_ga_approval_is_bound_to_version_commit_and_all_release_actions(
    tmp_path: Path,
) -> None:
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(_approval()), encoding="utf-8")

    approval = build_evidence.load_ga_approval(
        approval_path,
        version="2.0.0",
        commit=SOURCE_COMMIT,
        repository="Rath-Team/OpenRath",
        workflow_run_id="12345",
    )
    assert approval["approvers"] == ["release-owner"]

    missing_action = _approval()
    del missing_action["actions"]["pypi"]  # type: ignore[index]
    approval_path.write_text(json.dumps(missing_action), encoding="utf-8")
    with pytest.raises(ValueError, match="pypi"):
        build_evidence.load_ga_approval(
            approval_path,
            version="2.0.0",
            commit=SOURCE_COMMIT,
        )

    unsupported_action = _approval()
    unsupported_action["actions"]["tag"] = True  # type: ignore[index]
    approval_path.write_text(json.dumps(unsupported_action), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported actions"):
        build_evidence.load_ga_approval(
            approval_path,
            version="2.0.0",
            commit=SOURCE_COMMIT,
        )


def test_ga_approval_uses_actual_protected_environment_reviews(
    tmp_path: Path,
) -> None:
    history_path = tmp_path / "reviews.json"
    history_path.write_text(
        json.dumps(
            [
                {
                    "id": 42,
                    "state": "approved",
                    "user": {"login": "release-owner"},
                    "created_at": "2026-07-30T12:00:00Z",
                    "environments": [{"name": "ga-release"}],
                },
                {
                    "id": 43,
                    "state": "approved",
                    "user": {"login": "other-owner"},
                    "created_at": "2026-07-30T12:01:00Z",
                    "environments": [{"name": "staging"}],
                },
            ]
        ),
        encoding="utf-8",
    )

    approval = create_ga_approval.build_approval(
        version="2.0.0",
        source_commit=SOURCE_COMMIT,
        requested_by="release-requester",
        repository="Rath-Team/OpenRath",
        workflow_run_id="12345",
        review_history=history_path,
    )

    assert approval["approvers"] == ["release-owner"]
    assert approval["requested_by"] == "release-requester"
    assert approval["approved_at"] == "2026-07-30T12:00:00Z"
    assert approval["environment_reviews"] == [
        {
            "review_id": "42",
            "reviewer": "release-owner",
            "approved_at": "2026-07-30T12:00:00Z",
        }
    ]


def test_ga_release_requires_every_evidence_category() -> None:
    complete = set(build_evidence.GA_REQUIRED_ARTIFACTS)
    build_evidence.require_ga_artifacts(complete)

    incomplete = complete - {"soak"}
    with pytest.raises(ValueError, match="soak"):
        build_evidence.require_ga_artifacts(incomplete)


def test_verifier_accepts_legacy_rc_and_rejects_ga_with_blockers() -> None:
    legacy_rc = {
        "schema": "openrath.rc-evidence/1",
        "release_stage": "rc",
        "version": "2.0.0rc1",
        "tag": "v2.0.0rc1",
        "source_commit": SOURCE_COMMIT,
        "source_tree_clean": True,
        "ga_approved": False,
        "blocking_gates": ["target-like soak"],
        "artifacts": {},
    }
    verify_evidence.validate_release_state(
        legacy_rc,
        version="2.0.0rc1",
        commit=SOURCE_COMMIT,
    )

    ga = {
        **legacy_rc,
        "schema": "openrath.release-evidence/2",
        "release_stage": "ga",
        "version": "2.0.0",
        "tag": "v2.0.0",
        "ga_approved": True,
        "blocking_gates": ["not actually ready"],
        "approval": _approval(),
        "artifacts": {name: {} for name in build_evidence.GA_REQUIRED_ARTIFACTS},
    }
    with pytest.raises(AssertionError, match="blocking gates"):
        verify_evidence.validate_release_state(
            ga,
            version="2.0.0",
            commit=SOURCE_COMMIT,
        )


def test_release_manifest_schema_has_separate_rc_and_ga_contracts() -> None:
    schema = json.loads(
        Path("release/evidence/schema/manifest.schema.json").read_text(encoding="utf-8")
    )
    assert schema["$id"].endswith("/release-evidence-manifest-v2.json")
    assert len(schema["oneOf"]) == 2
