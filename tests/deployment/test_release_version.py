from __future__ import annotations

import json
import re
from pathlib import Path

RC_VERSION = "2.0.0rc1"


def test_release_candidate_version_surfaces_are_consistent() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', pyproject, flags=re.MULTILINE)
    assert match is not None
    assert match.group(1) == RC_VERSION

    openapi = json.loads(
        Path("deploy/docs/openapi-v2.json").read_text(encoding="utf-8")
    )
    assert openapi["info"]["version"] == RC_VERSION

    compose = Path("deploy/compose/compose.yaml").read_text(encoding="utf-8")
    kubernetes = Path("deploy/kubernetes/openrath.yaml").read_text(encoding="utf-8")
    assert compose.count(f"openrath:{RC_VERSION}") == 3
    assert kubernetes.count(f"openrath:{RC_VERSION}") == 3

    dockerfile = Path("docker/Dockerfile").read_text(encoding="utf-8")
    assert 'org.opencontainers.image.version="${OPENRATH_VERSION}"' in dockerfile
    assert 'org.opencontainers.image.revision="${OPENRATH_REVISION}"' in dockerfile

    assert Path(f"release/notes/v{RC_VERSION}.md").is_file()


def test_release_candidate_workflow_is_digest_and_evidence_bound() -> None:
    workflow = Path(".github/workflows/release-v2-rc.yml").read_text(encoding="utf-8")
    assert "packages: write" in workflow
    assert "attestations: write" in workflow
    assert "push: true" in workflow
    assert "steps.image.outputs.digest" in workflow
    assert "scripts/release/build_evidence.py" in workflow
    assert "scripts/release/verify_evidence.py" in workflow
    assert "--prerelease" in workflow
    assert "PyPI" not in workflow
