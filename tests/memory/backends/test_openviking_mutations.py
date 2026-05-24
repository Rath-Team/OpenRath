"""Write / Resource / Commit dispatch tests against a real OpenViking server.

The OpenViking SDK splits memory creation across three calls:

- ``write`` *updates* an existing memory file (created via session commit
  or seeded via ``add_resource``);
- ``add_resource`` *ingests* an external file/URL into ``viking://resources/``;
- ``commit_session`` archives a session's messages and triggers async
  memory extraction into ``viking://user/...``.

These tests exercise each path end-to-end against the live container.
"""

from __future__ import annotations

import os
import tempfile
import uuid

import pytest

from rath.memory import (
    MemoryCommitResult,
    MemoryExecutionFailure,
    MemoryOpCommit,
    MemoryOpRead,
    MemoryOpResource,
    MemoryOpWrite,
    MemoryStore,
    MemoryStoreSpec,
    MemoryWriteResult,
)
from rath.memory.adapters.openviking import OpenVikingBackend

pytestmark = pytest.mark.openviking


@pytest.fixture
def store(openviking_url: str, openviking_root_api_key: str) -> MemoryStore:
    backend = OpenVikingBackend()
    spec = MemoryStoreSpec(
        account_id="default",
        user_id="default",
        agent_id="default",
        options={"url": openviking_url, "api_key": openviking_root_api_key},
    )
    s = backend.open(spec)
    try:
        yield s
    finally:
        backend.close(s)


def _seed_writable_memory(openviking_url: str, openviking_root_api_key: str) -> str:
    """Seed a writable memory file via add_resource. Returns the file URI."""
    import openviking as _ov

    ns = "omut_" + uuid.uuid4().hex[:8]
    client = _ov.SyncHTTPClient(
        url=openviking_url,
        api_key=openviking_root_api_key,
        account="default",
        user_id="default",
        agent_id="default",
    )
    client.initialize()
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as fh:
            fh.write("# seed\nOriginal content.")
            local = fh.name
        try:
            client.add_resource(
                local,
                to=f"viking://resources/{ns}/",
                wait=True,
                timeout=60.0,
            )
        finally:
            os.unlink(local)
        listing = client.ls(f"viking://resources/{ns}")
        files = [e for e in listing if not e.get("isDir")]
        assert files, "seed failed"
        return files[0]["uri"]
    finally:
        client.close()


def test_write_updates_existing_memory_file(
    store: MemoryStore,
    openviking_url: str,
    openviking_root_api_key: str,
) -> None:
    seed_uri = _seed_writable_memory(openviking_url, openviking_root_api_key)
    new_content = "Replaced content: dark mode confirmed."
    op = MemoryOpWrite(uri=seed_uri, content=new_content, wait=False)
    result = store.dispatch(op)
    assert isinstance(result, MemoryWriteResult)
    assert result.uri == seed_uri
    assert result.bytes_written == len(new_content.encode("utf-8"))
    # Round-trip
    read = store.dispatch(MemoryOpRead(uri=seed_uri, level="detail"))
    text = read.data if isinstance(read.data, str) else read.data.decode("utf-8")
    assert text == new_content


def test_write_to_invalid_scope_returns_failure(store: MemoryStore) -> None:
    op = MemoryOpWrite(
        uri="viking://bogus_scope_xyz/x.txt",
        content="x",
    )
    result = store.dispatch(op)
    assert isinstance(result, MemoryExecutionFailure)
    assert result.kind == "invalid_uri"


def test_resource_ingest_creates_file(store: MemoryStore) -> None:
    ns = "ores_" + uuid.uuid4().hex[:8]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as fh:
        fh.write("Resource ingest test content for OpenRath.")
        local = fh.name
    try:
        op = MemoryOpResource(
            source=local,
            target_uri=f"viking://resources/{ns}/",
            wait=True,
            timeout_seconds=60.0,
        )
        result = store.dispatch(op)
    finally:
        os.unlink(local)
    assert isinstance(result, MemoryWriteResult)
    assert result.uri  # non-empty


def test_commit_archives_session_and_returns_task_id(
    store: MemoryStore,
) -> None:
    sid = "ocommit_" + uuid.uuid4().hex[:8]
    op = MemoryOpCommit(
        session_id=sid,
        messages=(
            {
                "role": "user",
                "content": "Please remember: my favorite test fixture phrase is 'rainbow-platypus-9'.",
            },
            {
                "role": "assistant",
                "content": "Noted: 'rainbow-platypus-9' as your favorite test fixture phrase.",
            },
        ),
        wait=False,  # extraction takes ~15s, just check commit accepted
    )
    result = store.dispatch(op)
    assert isinstance(result, MemoryCommitResult)
    assert result.task_id and isinstance(result.task_id, str)
    assert result.archived_uri and result.archived_uri.startswith(
        f"viking://session/{sid}/"
    )
