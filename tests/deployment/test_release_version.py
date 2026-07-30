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


def test_ga_workflow_is_protected_evidence_bound_and_uses_trusted_publishing() -> None:
    workflow = Path(".github/workflows/release-v2-ga.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "evidence_run_id:" in workflow
    assert "confirmation:" in workflow
    assert "name: ga-release" in workflow
    assert "scripts/release/verify_gate_reports.py" in workflow
    assert "--stage ga" in workflow
    assert "--approval" in workflow
    assert "openrath-v2.0.0-ga-input" in workflow
    assert "actions: read" in workflow
    assert "packages: write" in workflow
    assert "attestations: write" in workflow
    assert "id-token: write" in workflow
    assert (
        "pypa/gh-action-pypi-publish"
        "@dc37677b2e1c63e2034f94d8a5b11f265b73ba33" in workflow
    )
    assert "scripts/release/verify_pypi_files.py" in workflow
    assert "skip-existing: true" in workflow
    assert "--require-complete" in workflow
    assert "gh release create" in workflow
    assert "--prerelease" not in workflow


def test_ga_release_documents_are_present_and_not_marked_as_drafts() -> None:
    notes = Path("release/notes/v2.0.0.md").read_text(encoding="utf-8")
    checklist = Path("release/checklists/v2.0.0-ga.md").read_text(encoding="utf-8")
    assert "OpenRath v2.0.0" in notes
    assert "Gate C" in checklist
    for marker in ("TODO", "HOLD", "DRAFT"):
        assert marker not in notes
