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


def test_ga_workflows_separate_preparation_manual_pypi_and_finalization() -> None:
    prepare = Path(".github/workflows/release-v2-ga.yml").read_text(encoding="utf-8")
    finalize = Path(".github/workflows/release-v2-ga-finalize.yml").read_text(
        encoding="utf-8"
    )
    workflows = prepare + finalize

    assert "workflow_dispatch:" in prepare
    assert "evidence_run_id:" in prepare
    assert "name: ga-release" in prepare
    assert "scripts/release/verify_gate_reports.py" in prepare
    assert "--stage ga" in prepare
    assert "--approval" in prepare
    assert "openrath-v2.0.0-ga-input" in prepare
    assert "openrath-2.0.0-ga-candidate" in workflows
    assert "attestations: write" in prepare
    assert "pypa/gh-action-pypi-publish" not in workflows
    assert "TWINE_PASSWORD" not in workflows
    assert "id-token: write" in prepare
    assert "id-token: write" not in finalize

    assert "preparation_run_id:" in finalize
    assert "workflowName" in finalize
    assert "--artifact-root release-bundle" in finalize
    assert "scripts/release/verify_pypi_files.py" in finalize
    assert "--require-complete" in finalize
    assert "imagetools create" in finalize
    assert "gh release create" in finalize
    assert "--prerelease" not in workflows

    manual = Path("scripts/release/publish_pypi_manual.py").read_text(encoding="utf-8")
    assert '"__token__"' in manual
    assert '"--password"' not in manual
    assert "twine=={TWINE_VERSION}" in manual
    assert Path("release/manual-pypi-v2.0.0.md").is_file()


def test_ga_release_documents_are_present_and_not_marked_as_drafts() -> None:
    notes = Path("release/notes/v2.0.0.md").read_text(encoding="utf-8")
    checklist = Path("release/checklists/v2.0.0-ga.md").read_text(encoding="utf-8")
    assert "OpenRath v2.0.0" in notes
    assert "Gate C" in checklist
    assert "Trusted Publishing" not in checklist
    for marker in ("TODO", "HOLD", "DRAFT"):
        assert marker not in notes
