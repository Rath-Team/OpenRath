from __future__ import annotations

import io
from pathlib import Path

import pytest

from rath.artifacts import ArtifactNotFound, LocalArtifactStore, S3ArtifactStore


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
    payload = tmp_path / "artifacts" / "tenant" / artifact.digest[:2] / artifact.digest
    payload.write_bytes(b"corrupt")
    with pytest.raises(OSError, match="verification"):
        store.get("tenant", artifact.digest)
    assert store.delete("tenant", artifact.digest)
    assert not store.delete("tenant", artifact.digest)


def test_s3_artifact_stops_reading_after_configured_limit() -> None:
    class _Client:
        def put_object(self, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("oversized content must not be uploaded")

    class _Stream:
        def __init__(self) -> None:
            self.reads = 0

        def read(self, size: int) -> bytes:
            self.reads += 1
            return b"x" * size

    stream = _Stream()
    store = S3ArtifactStore(
        "bucket",
        client=_Client(),
        max_bytes=3,
    )

    with pytest.raises(ValueError, match="size"):
        store.put("tenant", stream)
    assert stream.reads == 1


def test_s3_artifact_streams_staged_payload_and_cleans_orphan() -> None:
    class _Client:
        def __init__(self) -> None:
            self.calls = 0
            self.deleted: list[str] = []

        def put_object(self, **kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                body = kwargs["Body"]
                assert not isinstance(body, bytes)
                assert body.read() == b"streamed"
                return {}
            raise RuntimeError("manifest failed")

        def delete_objects(self, **kwargs):  # type: ignore[no-untyped-def]
            self.deleted.extend(item["Key"] for item in kwargs["Delete"]["Objects"])

    client = _Client()
    store = S3ArtifactStore("bucket", client=client)

    with pytest.raises(RuntimeError, match="manifest"):
        store.put("tenant", io.BytesIO(b"streamed"))

    assert len(client.deleted) == 1
    assert not client.deleted[0].endswith(".json")
