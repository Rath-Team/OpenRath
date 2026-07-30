"""Build a SHA-bound OpenRath RC or GA evidence manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

RELEASE_SCHEMA = "openrath.release-evidence/2"
RC_BLOCKING_GATES = (
    "approved live LLM/provider lifecycle",
    "approved live OpenViking lifecycle",
    "target-like capacity and one-to-four worker scaling",
    "eight-hour target-like soak",
    "target-cluster backup/restore and rollout/rollback drills",
    "final API stability, v1 maintenance window, and GA owner approval",
)
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


def infer_release_stage(version: str) -> str:
    """Return the only supported release stage for a v2.0.0 version."""
    if re.fullmatch(r"2\.0\.0rc[1-9][0-9]*", version):
        return "rc"
    if version == "2.0.0":
        return "ga"
    raise ValueError(f"unsupported release version: {version!r}")


def load_ga_approval(
    path: Path,
    *,
    version: str,
    commit: str,
    repository: str | None = None,
    workflow_run_id: str | None = None,
) -> dict[str, object]:
    """Load and validate an explicit owner approval bound to the GA SHA."""
    approval = json.loads(path.read_text(encoding="utf-8"))
    if approval.get("schema") != "openrath.ga-approval/1":
        raise ValueError("GA approval schema must be openrath.ga-approval/1")
    if approval.get("version") != version:
        raise ValueError("GA approval version does not match the release")
    if approval.get("source_commit") != commit:
        raise ValueError("GA approval source_commit does not match HEAD")
    if approval.get("approved") is not True:
        raise ValueError("GA approval must set approved=true")
    if approval.get("environment") != "ga-release":
        raise ValueError("GA approval environment must be ga-release")
    approval_repository = approval.get("repository")
    if (
        not isinstance(approval_repository, str)
        or re.fullmatch(r"[^/\s]+/[^/\s]+", approval_repository) is None
    ):
        raise ValueError("GA approval repository must be owner/name")
    if repository is not None and approval.get("repository") != repository:
        raise ValueError("GA approval repository does not match the workflow")
    approval_run_id = approval.get("workflow_run_id")
    if re.fullmatch(r"[1-9][0-9]*", str(approval_run_id or "")) is None:
        raise ValueError("GA approval workflow_run_id must be a positive integer")
    if (
        workflow_run_id is not None
        and approval.get("workflow_run_id") != workflow_run_id
    ):
        raise ValueError("GA approval workflow_run_id does not match the workflow")
    requested_by = approval.get("requested_by")
    if not isinstance(requested_by, str) or not requested_by.strip():
        raise ValueError("GA approval requires requested_by")
    approvers = approval.get("approvers")
    if (
        not isinstance(approvers, list)
        or not approvers
        or any(not isinstance(item, str) or not item.strip() for item in approvers)
        or len(set(approvers)) != len(approvers)
    ):
        raise ValueError("GA approval requires unique non-empty approvers")
    environment_reviews = approval.get("environment_reviews")
    if not isinstance(environment_reviews, list) or not environment_reviews:
        raise ValueError("GA approval requires environment reviews")
    review_approvers: set[str] = set()
    review_ids: set[str] = set()
    review_times: list[datetime] = []
    for review in environment_reviews:
        if not isinstance(review, dict):
            raise ValueError("GA approval environment review must be an object")
        review_id = str(review.get("review_id", ""))
        if re.fullmatch(r"[1-9][0-9]*", review_id) is None:
            raise ValueError("GA approval review_id must be a positive integer")
        if review_id in review_ids:
            raise ValueError("GA approval review ids must be unique")
        review_ids.add(review_id)
        reviewer = review.get("reviewer")
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise ValueError("GA approval environment review requires reviewer")
        review_approvers.add(reviewer)
        review_approved_at = review.get("approved_at")
        if not isinstance(review_approved_at, str):
            raise ValueError("GA approval environment review requires approved_at")
        try:
            parsed_review_time = datetime.fromisoformat(
                review_approved_at.replace("Z", "+00:00")
            )
        except ValueError as error:
            raise ValueError(
                "GA approval environment review approved_at must be ISO 8601"
            ) from error
        if parsed_review_time.tzinfo is None:
            raise ValueError(
                "GA approval environment review approved_at requires a timezone"
            )
        review_times.append(parsed_review_time)
    if review_approvers != set(approvers):
        raise ValueError("GA approval approvers do not match environment reviews")
    approved_at = approval.get("approved_at")
    if not isinstance(approved_at, str):
        raise ValueError("GA approval requires approved_at")
    try:
        parsed_approved_at = datetime.fromisoformat(approved_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("GA approval approved_at must be ISO 8601") from error
    if parsed_approved_at.tzinfo is None:
        raise ValueError("GA approval approved_at must include a timezone")
    if parsed_approved_at != max(review_times):
        raise ValueError("GA approval approved_at must match the latest review")
    actions = approval.get("actions")
    if not isinstance(actions, dict):
        raise ValueError("GA approval requires release actions")
    missing_actions = sorted(
        action for action in GA_RELEASE_ACTIONS if actions.get(action) is not True
    )
    if missing_actions:
        raise ValueError(
            "GA approval is missing affirmative actions: " + ", ".join(missing_actions)
        )
    unexpected_actions = sorted(set(actions) - GA_RELEASE_ACTIONS)
    if unexpected_actions:
        raise ValueError(
            "GA approval contains unsupported actions: " + ", ".join(unexpected_actions)
        )
    return approval


def require_ga_artifacts(names: set[str]) -> None:
    """Fail unless every GA evidence category is present."""
    missing = sorted(GA_REQUIRED_ARTIFACTS - names)
    if missing:
        raise ValueError("GA evidence is missing artifacts: " + ", ".join(missing))


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


def _git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", *arguments],
        text=True,
        encoding="utf-8",
    ).strip()


def _artifact(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "path": path.as_posix(),
        "size": path.stat().st_size,
        "sha256": _sha256(path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--stage", choices=("rc", "ga"))
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--image-ref", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="additional report or artifact to hash",
    )
    args = parser.parse_args()

    version = _project_version()
    if args.tag != f"v{version}":
        raise SystemExit(f"tag {args.tag!r} does not match project version {version!r}")
    try:
        release_stage = infer_release_stage(version)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if args.stage is not None and args.stage != release_stage:
        raise SystemExit(
            f"stage {args.stage!r} does not match release version {version!r}"
        )
    if re.fullmatch(r"sha256:[0-9a-f]{64}", args.image_digest) is None:
        raise SystemExit("image digest must be sha256 followed by 64 lowercase hex")

    commit = _git("rev-parse", "HEAD")
    wheel = next(Path("dist").glob(f"openrath-{version}-*.whl"))
    sdist = Path("dist") / f"openrath-{version}.tar.gz"
    artifacts: dict[str, object] = {
        "wheel": _artifact(wheel),
        "sdist": _artifact(sdist),
        "openapi": _artifact(Path("deploy/docs/openapi-v2.json")),
        "image": {
            "reference": args.image_ref,
            "digest": args.image_digest,
        },
    }
    for item in args.artifact:
        name, separator, raw_path = item.partition("=")
        if not separator or not name or not raw_path:
            raise SystemExit(f"invalid --artifact value: {item!r}")
        if name in artifacts:
            raise SystemExit(f"duplicate artifact name: {name}")
        artifacts[name] = _artifact(Path(raw_path))

    approval_summary: dict[str, object] | None = None
    if release_stage == "ga":
        if args.approval is None:
            raise SystemExit("GA evidence requires --approval")
        try:
            approval = load_ga_approval(
                args.approval,
                version=version,
                commit=commit,
                repository=os.getenv("GITHUB_REPOSITORY"),
                workflow_run_id=os.getenv("GITHUB_RUN_ID"),
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise SystemExit(f"invalid GA approval: {error}") from error
        if "approval" in artifacts:
            raise SystemExit("approval artifact is reserved for --approval")
        artifacts["approval"] = _artifact(args.approval)
        try:
            require_ga_artifacts(set(artifacts))
        except ValueError as error:
            raise SystemExit(str(error)) from error
        approval_summary = {
            "approvers": approval["approvers"],
            "requested_by": approval["requested_by"],
            "approved_at": approval["approved_at"],
            "environment": approval["environment"],
            "workflow_run_id": approval["workflow_run_id"],
            "source_commit": approval["source_commit"],
            "actions": approval["actions"],
        }
        blocking_gates: list[str] = []
    else:
        if args.approval is not None:
            raise SystemExit("--approval is only valid for a GA release")
        blocking_gates = list(RC_BLOCKING_GATES)

    tracked_status = _git("status", "--porcelain", "--untracked-files=no")
    manifest = {
        "schema": RELEASE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_stage": release_stage,
        "version": version,
        "tag": args.tag,
        "source_commit": commit,
        "source_tree_clean": not tracked_status,
        "base_commit": _git("merge-base", "HEAD", "origin/main"),
        "ga_approved": release_stage == "ga",
        "workflow": {
            "repository": os.getenv("GITHUB_REPOSITORY"),
            "run_id": os.getenv("GITHUB_RUN_ID"),
            "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT"),
        },
        "artifacts": artifacts,
        "blocking_gates": blocking_gates,
    }
    if approval_summary is not None:
        manifest["approval"] = approval_summary
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
