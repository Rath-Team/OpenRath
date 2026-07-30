from __future__ import annotations

from pathlib import Path

from rath.deployment import DeploymentManifest, Revision, SQLiteRevisionStore
from rath.runtime import SQLiteRunStore


def test_revision_identity_is_deterministic_and_persistent(tmp_path: Path) -> None:
    manifest = DeploymentManifest(
        image_digest="a" * 64,
        plan_hash="b" * 64,
        python_version="3.12",
        dependencies_digest="c" * 64,
        resources={"provider": "openai"},
    )
    first = Revision.create(code_digest="d" * 64, manifest=manifest)
    second = Revision.create(code_digest="d" * 64, manifest=manifest)
    run_store = SQLiteRunStore(tmp_path / "runtime.db")
    store = SQLiteRevisionStore(run_store)

    store.put(first)

    assert first.id == second.id
    assert first.content_digest == second.content_digest
    assert len(first.content_digest) == 64
    assert store.get(first.id) == first
    assert store.put(second).id == first.id


def test_manifest_change_changes_revision_content_identity() -> None:
    first_manifest = DeploymentManifest(
        image_digest="a" * 64,
        plan_hash="b" * 64,
        python_version="3.12",
        dependencies_digest="c" * 64,
    )
    second_manifest = DeploymentManifest(
        image_digest="a" * 64,
        plan_hash="e" * 64,
        python_version="3.12",
        dependencies_digest="c" * 64,
    )

    first = Revision.create(code_digest="d" * 64, manifest=first_manifest)
    second = Revision.create(code_digest="d" * 64, manifest=second_manifest)

    assert first.id != second.id
    assert first.content_digest != second.content_digest
