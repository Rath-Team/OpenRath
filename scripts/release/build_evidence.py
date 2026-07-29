"""Build a SHA-bound OpenRath release-candidate evidence manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


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
    if re.fullmatch(r"sha256:[0-9a-f]{64}", args.image_digest) is None:
        raise SystemExit("image digest must be sha256 followed by 64 lowercase hex")

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

    commit = _git("rev-parse", "HEAD")
    tracked_status = _git("status", "--porcelain", "--untracked-files=no")
    manifest = {
        "schema": "openrath.rc-evidence/1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_stage": "rc",
        "version": version,
        "tag": args.tag,
        "source_commit": commit,
        "source_tree_clean": not tracked_status,
        "base_commit": _git("merge-base", "HEAD", "origin/main"),
        "ga_approved": False,
        "workflow": {
            "repository": os.getenv("GITHUB_REPOSITORY"),
            "run_id": os.getenv("GITHUB_RUN_ID"),
            "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT"),
        },
        "artifacts": artifacts,
        "blocking_gates": [
            "approved live LLM/provider lifecycle",
            "approved live OpenViking lifecycle",
            "target-like capacity and one-to-four worker scaling",
            "eight-hour target-like soak",
            "target-cluster backup/restore and rollout/rollback drills",
            "final API stability, v1 maintenance window, and GA owner approval",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
