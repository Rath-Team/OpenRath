"""Verify an OpenRath release-candidate evidence manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    version = _project_version()
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        text=True,
        encoding="utf-8",
    ).strip()

    assert manifest["schema"] == "openrath.rc-evidence/1"
    assert manifest["release_stage"] == "rc"
    assert manifest["version"] == version
    assert manifest["tag"] == f"v{version}"
    assert manifest["source_commit"] == commit
    assert manifest["source_tree_clean"] is True
    assert manifest["ga_approved"] is False
    assert manifest["blocking_gates"]

    openapi = json.loads(
        Path("deploy/docs/openapi-v2.json").read_text(encoding="utf-8")
    )
    assert openapi["info"]["version"] == version

    for name, artifact in manifest["artifacts"].items():
        if name == "image":
            assert re.fullmatch(r"sha256:[0-9a-f]{64}", artifact["digest"])
            continue
        path = Path(artifact["path"])
        assert path.is_file(), path
        assert path.stat().st_size == artifact["size"], path
        assert _sha256(path) == artifact["sha256"], path

    print(
        f"verified {manifest['tag']} evidence for "
        f"{manifest['source_commit']} ({len(manifest['artifacts'])} artifacts)"
    )


if __name__ == "__main__":
    main()
