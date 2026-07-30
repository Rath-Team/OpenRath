"""Verify an OpenRath RC or GA evidence manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

try:
    from .build_evidence import load_ga_approval
except ImportError:  # pragma: no cover - direct script execution
    from build_evidence import load_ga_approval

LEGACY_RC_SCHEMA = "openrath.rc-evidence/1"
RELEASE_SCHEMA = "openrath.release-evidence/2"
GA_RELEASE_ACTIONS = frozenset(
    {
        "pypi",
        "ghcr",
        "github_release",
    }
)
GA_REQUIRED_ARTIFACTS = frozenset(
    {
        "approval",
        "tests",
        "live_adapters",
        "performance",
        "soak",
        "drills",
        "compatibility",
        "sbom",
        "image_scan",
        "secret_scan",
        "dependency_audit_production",
        "dependency_audit_all",
        "kubernetes",
    }
)


def validate_release_state(
    manifest: dict[str, object],
    *,
    version: str,
    commit: str,
) -> None:
    """Validate stage, version, approval, and blocker invariants."""
    assert manifest["version"] == version
    assert manifest["tag"] == f"v{version}"
    assert manifest["source_commit"] == commit
    assert manifest["source_tree_clean"] is True

    schema = manifest["schema"]
    stage = manifest["release_stage"]
    if schema == LEGACY_RC_SCHEMA:
        assert stage == "rc"
        assert re.fullmatch(r"2\.0\.0rc[1-9][0-9]*", version)
        assert manifest["ga_approved"] is False
        assert manifest["blocking_gates"], "legacy RC requires blocking gates"
        return

    assert schema == RELEASE_SCHEMA
    if stage == "rc":
        assert re.fullmatch(r"2\.0\.0rc[1-9][0-9]*", version)
        assert manifest["ga_approved"] is False
        assert manifest["blocking_gates"], "RC requires blocking gates"
        assert "approval" not in manifest
        return

    assert stage == "ga"
    assert version == "2.0.0"
    assert manifest["ga_approved"] is True
    assert not manifest["blocking_gates"], "GA cannot contain blocking gates"
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, dict)
    missing_artifacts = sorted(GA_REQUIRED_ARTIFACTS - set(artifacts))
    assert not missing_artifacts, "GA evidence is missing artifacts: " + ", ".join(
        missing_artifacts
    )
    approval = manifest.get("approval")
    assert isinstance(approval, dict), "GA requires approval metadata"
    assert approval.get("source_commit") == commit
    assert approval.get("environment") == "ga-release"
    assert isinstance(approval.get("requested_by"), str) and approval["requested_by"]
    approvers = approval.get("approvers")
    assert isinstance(approvers, list) and approvers
    assert all(isinstance(approver, str) and approver for approver in approvers)
    assert len(set(approvers)) == len(approvers)
    assert re.fullmatch(r"[1-9][0-9]*", str(approval.get("workflow_run_id", "")))
    assert approval.get("approved_at")
    actions = approval.get("actions")
    assert isinstance(actions, dict)
    missing_actions = sorted(
        action for action in GA_RELEASE_ACTIONS if actions.get(action) is not True
    )
    assert not missing_actions, "GA approval is missing actions: " + ", ".join(
        missing_actions
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _project_version() -> str:
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', text, flags=re.MULTILINE)
    if match is None:
        raise RuntimeError("project version is missing from pyproject.toml")
    return match.group(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("."),
        help="root directory used to resolve artifact paths from the manifest",
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    version = _project_version()
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        text=True,
        encoding="utf-8",
    ).strip()

    validate_release_state(manifest, version=version, commit=commit)

    openapi = json.loads(
        Path("deploy/docs/openapi-v2.json").read_text(encoding="utf-8")
    )
    assert openapi["info"]["version"] == version

    for name, artifact in manifest["artifacts"].items():
        if name == "image":
            assert re.fullmatch(r"sha256:[0-9a-f]{64}", artifact["digest"])
            continue
        path = args.artifact_root / artifact["path"]
        assert path.is_file(), path
        assert path.stat().st_size == artifact["size"], path
        assert _sha256(path) == artifact["sha256"], path

    if manifest["release_stage"] == "ga":
        approval_path = args.artifact_root / manifest["artifacts"]["approval"]["path"]
        workflow = manifest.get("workflow")
        assert isinstance(workflow, dict)
        workflow_repository = workflow.get("repository")
        workflow_run_id = workflow.get("run_id")
        assert isinstance(workflow_repository, str) and workflow_repository
        assert isinstance(workflow_run_id, str) and workflow_run_id
        approval = load_ga_approval(
            approval_path,
            version=version,
            commit=commit,
            repository=workflow_repository,
            workflow_run_id=workflow_run_id,
        )
        assert approval["approvers"] == manifest["approval"]["approvers"]
        assert approval["requested_by"] == manifest["approval"]["requested_by"]
        assert approval["approved_at"] == manifest["approval"]["approved_at"]
        assert approval["environment"] == manifest["approval"]["environment"]
        assert approval["workflow_run_id"] == manifest["approval"]["workflow_run_id"]
        assert approval["actions"] == manifest["approval"]["actions"]

    print(
        f"verified {manifest['tag']} evidence for "
        f"{manifest['source_commit']} ({len(manifest['artifacts'])} artifacts)"
    )


if __name__ == "__main__":
    main()
