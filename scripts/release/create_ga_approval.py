"""Create a workflow-bound GA approval record after environment approval."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

GA_ACTIONS = {
    "pypi": True,
    "ghcr": True,
    "github_release": True,
}
GA_ENVIRONMENT = "ga-release"


def _environment_reviews(path: Path) -> list[dict[str, str]]:
    """Extract approved GA environment reviews from GitHub's run history."""
    history = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(history, list):
        raise ValueError("review history must be a JSON array")

    reviews: list[dict[str, str]] = []
    for review in history:
        if not isinstance(review, dict) or review.get("state") != "approved":
            continue
        environments = review.get("environments")
        if not isinstance(environments, list) or not any(
            isinstance(environment, dict) and environment.get("name") == GA_ENVIRONMENT
            for environment in environments
        ):
            continue
        review_id = review.get("id")
        user = review.get("user")
        created_at = review.get("created_at")
        reviewer = user.get("login") if isinstance(user, dict) else None
        if not isinstance(review_id, int) or review_id < 1:
            raise ValueError("approved review requires a positive integer id")
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise ValueError("approved review requires user.login")
        if not isinstance(created_at, str):
            raise ValueError("approved review requires created_at")
        try:
            parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("approved review created_at must be ISO 8601") from error
        if parsed.tzinfo is None:
            raise ValueError("approved review created_at must include a timezone")
        reviews.append(
            {
                "review_id": str(review_id),
                "reviewer": reviewer,
                "approved_at": created_at,
            }
        )

    if not reviews:
        raise ValueError(f"no approved {GA_ENVIRONMENT} environment review found")
    review_ids = [review["review_id"] for review in reviews]
    if len(set(review_ids)) != len(review_ids):
        raise ValueError("approved environment review ids must be unique")
    return sorted(reviews, key=lambda item: (item["approved_at"], item["review_id"]))


def build_approval(
    *,
    version: str,
    source_commit: str,
    requested_by: str,
    repository: str,
    workflow_run_id: str,
    review_history: Path,
) -> dict[str, object]:
    """Build an approval record bound to one protected workflow run."""
    if version != "2.0.0":
        raise ValueError("GA approval version must be 2.0.0")
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ValueError("source_commit must be 40 lowercase hexadecimal characters")
    if not requested_by.strip():
        raise ValueError("requested_by is required")
    if not repository.strip():
        raise ValueError("repository is required")
    if re.fullmatch(r"[1-9][0-9]*", workflow_run_id) is None:
        raise ValueError("workflow_run_id must be a positive integer")
    environment_reviews = _environment_reviews(review_history)
    approvers = sorted({review["reviewer"] for review in environment_reviews})
    return {
        "schema": "openrath.ga-approval/1",
        "version": version,
        "source_commit": source_commit,
        "approved": True,
        "approved_at": environment_reviews[-1]["approved_at"],
        "approvers": approvers,
        "requested_by": requested_by,
        "environment": GA_ENVIRONMENT,
        "environment_reviews": environment_reviews,
        "repository": repository,
        "workflow_run_id": workflow_run_id,
        "actions": dict(GA_ACTIONS),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--requested-by", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--review-history", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    approval = build_approval(
        version=args.version,
        source_commit=args.source_commit,
        requested_by=args.requested_by,
        repository=args.repository,
        workflow_run_id=args.workflow_run_id,
        review_history=args.review_history,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(approval, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
