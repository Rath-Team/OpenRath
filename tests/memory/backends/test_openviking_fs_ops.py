"""Dispatch tests for Read / List / Tree against a real OpenViking server.

Seed approach (no mocks): we use the live ``add_resource`` SDK call --
which is the only way to materialise a file under
``viking://resources/...`` on the server -- to drop a known fixture in
place, wait for indexing, then exercise the adapter's
:class:`MemoryOpRead` / :class:`MemoryOpList` / :class:`MemoryOpTree`
through its public ``store.dispatch(...)`` surface.
"""

from __future__ import annotations

import os
import tempfile
import uuid

import pytest

from rath.memory import (
    MemoryEntry,
    MemoryListResult,
    MemoryReadResult,
    MemoryStore,
    MemoryStoreSpec,
)
from rath.memory.adapters.openviking import OpenVikingBackend

pytestmark = pytest.mark.openviking


@pytest.fixture(scope="module")
def seeded_resource_namespace(
    openviking_url: str, openviking_root_api_key: str
) -> dict[str, str]:
    """Drop a fixture file into a fresh ``viking://resources/<ns>/`` directory.

    Returns a mapping ``{"namespace_uri": ..., "file_uri": ..., "content": ...}``.
    """
    import openviking as _ov

    ns = "ofs_" + uuid.uuid4().hex[:8]
    content = "OpenRath FS ops test fixture content."
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
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(content)
            local_path = fh.name
        try:
            result = client.add_resource(
                local_path,
                to=f"viking://resources/{ns}/",
                wait=True,
                timeout=60.0,
            )
        finally:
            os.unlink(local_path)
        # add_resource creates a temp-named file inside the target directory;
        # locate it via ls so the test doesn't depend on internal naming.
        listing = client.ls(f"viking://resources/{ns}")
        files = [e for e in listing if not e.get("isDir")]
        assert files, f"seed failed: no file produced under {ns}; {result!r}"
        file_uri = files[0]["uri"]
    finally:
        client.close()
    return {
        "namespace_uri": f"viking://resources/{ns}",
        "file_uri": file_uri,
        "content": content,
    }


@pytest.fixture
def store(openviking_url: str, openviking_root_api_key: str) -> "MemoryStore":
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


def test_read_detail_returns_full_content(
    store: MemoryStore, seeded_resource_namespace: dict[str, str]
) -> None:
    from rath.memory import MemoryOpRead

    op = MemoryOpRead(uri=seeded_resource_namespace["file_uri"], level="detail")
    result = store.dispatch(op)
    assert isinstance(result, MemoryReadResult)
    assert result.level == "detail"
    assert result.uri == op.uri
    text = result.data if isinstance(result.data, str) else result.data.decode("utf-8")
    assert seeded_resource_namespace["content"] in text


def test_read_abstract_on_directory_returns_summary(
    store: MemoryStore, seeded_resource_namespace: dict[str, str]
) -> None:
    """The OpenViking server only exposes abstract/overview on directories
    (files raise FailedPreconditionError). The adapter passes the level
    straight through; this test pins that behaviour for L0 against a dir."""
    from rath.memory import MemoryOpRead

    op = MemoryOpRead(uri=seeded_resource_namespace["namespace_uri"], level="abstract")
    result = store.dispatch(op)
    assert isinstance(result, MemoryReadResult)
    assert result.level == "abstract"
    text = result.data if isinstance(result.data, str) else result.data.decode("utf-8")
    assert isinstance(text, str)


def test_read_overview_on_directory_returns_navigable_summary(
    store: MemoryStore, seeded_resource_namespace: dict[str, str]
) -> None:
    from rath.memory import MemoryOpRead

    op = MemoryOpRead(uri=seeded_resource_namespace["namespace_uri"], level="overview")
    result = store.dispatch(op)
    assert isinstance(result, MemoryReadResult)
    assert result.level == "overview"
    text = result.data if isinstance(result.data, str) else result.data.decode("utf-8")
    assert isinstance(text, str)


def test_list_returns_entries_for_namespace(
    store: MemoryStore, seeded_resource_namespace: dict[str, str]
) -> None:
    from rath.memory import MemoryOpList

    op = MemoryOpList(uri=seeded_resource_namespace["namespace_uri"])
    result = store.dispatch(op)
    assert isinstance(result, MemoryListResult)
    assert result.entries, "expected at least one entry"
    file_entry = next(
        (e for e in result.entries if e.uri == seeded_resource_namespace["file_uri"]),
        None,
    )
    assert file_entry is not None
    assert isinstance(file_entry, MemoryEntry)
    assert file_entry.is_dir is False
    assert file_entry.size is not None and file_entry.size > 0


def test_tree_returns_flattened_entries(
    store: MemoryStore, seeded_resource_namespace: dict[str, str]
) -> None:
    from rath.memory import MemoryOpTree

    op = MemoryOpTree(uri=seeded_resource_namespace["namespace_uri"], depth=3)
    result = store.dispatch(op)
    assert isinstance(result, MemoryListResult)
    uris = {e.uri for e in result.entries}
    assert seeded_resource_namespace["file_uri"] in uris


def test_read_missing_uri_returns_not_found_failure(store: MemoryStore) -> None:
    from rath.memory import MemoryExecutionFailure, MemoryOpRead

    op = MemoryOpRead(
        uri="viking://user/default/__definitely_does_not_exist_" + uuid.uuid4().hex,
        level="detail",
    )
    result = store.dispatch(op)
    assert isinstance(result, MemoryExecutionFailure)
    assert result.kind == "not_found"
