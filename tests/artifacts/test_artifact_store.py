from __future__ import annotations

import io
from pathlib import Path

import pytest

from rath.artifacts import ArtifactNotFound, LocalArtifactStore


def test_local_artifact_is_content_addressed_and_tenant_scoped(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    first = store.put(
        "tenant-a",
        io.BytesIO(b"durable result"),
        media_type="text/plain",
        metadata={"run_id": "run-1"},
    )
    duplicate = store.put("tenant-a", b"durable result", media_type="text/plain")

    assert first.digest == duplicate.digest
    assert first.uri.startswith("artifact://tenant-a/")
    assert store.get("tenant-a", first.digest) == b"durable result"
    with pytest.raises(ArtifactNotFound):
        store.get("tenant-b", first.digest)


def test_local_artifact_enforces_size_identity_and_deletion(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts", max_bytes=3)
    with pytest.raises(ValueError, match="size"):
        store.put("tenant", b"four")
    with pytest.raises(ValueError, match="unsafe"):
        store.put("../tenant", b"x")

    artifact = store.put("tenant", b"one")
    payload = (
        tmp_path
        / "artifacts"
        / "tenant"
        / artifact.digest[:2]
        / artifact.digest
    )
    payload.write_bytes(b"corrupt")
    with pytest.raises(OSError, match="verification"):
        store.get("tenant", artifact.digest)
    assert store.delete("tenant", artifact.digest)
    assert not store.delete("tenant", artifact.digest)
