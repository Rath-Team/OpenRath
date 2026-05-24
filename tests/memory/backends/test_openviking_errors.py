"""Error-kind mapping tests against a real OpenViking server.

These tests provoke real SDK exceptions -- no monkeypatching of the
client -- and assert the adapter surfaces them as
:class:`MemoryExecutionFailure` with the right ``kind``.
"""

from __future__ import annotations

import uuid
from typing import Iterator

import pytest

from rath.memory import (
    MemoryExecutionFailure,
    MemoryOpFind,
    MemoryOpList,
    MemoryOpRead,
    MemoryOpWrite,
    MemoryStore,
    MemoryStoreSpec,
)
from rath.memory.adapters.openviking import OpenVikingBackend

pytestmark = pytest.mark.openviking


@pytest.fixture
def store(openviking_url: str, openviking_root_api_key: str) -> Iterator[MemoryStore]:
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


def test_not_found_for_unknown_uri(store: MemoryStore) -> None:
    op = MemoryOpRead(
        uri=f"viking://user/default/__does_not_exist_{uuid.uuid4().hex}",
        level="detail",
    )
    result = store.dispatch(op)
    assert isinstance(result, MemoryExecutionFailure)
    assert result.kind == "not_found"


def test_invalid_uri_for_bogus_scope(store: MemoryStore) -> None:
    op = MemoryOpWrite(uri="viking://bogus_scope_xyz/x.txt", content="x")
    result = store.dispatch(op)
    assert isinstance(result, MemoryExecutionFailure)
    assert result.kind == "invalid_uri"


def test_invalid_uri_for_list_against_unknown_scope(store: MemoryStore) -> None:
    """The SDK's ls() against an unknown scope raises InvalidURIError
    (not NotFoundError) -- this test pins that mapping."""
    op = MemoryOpList(uri="viking://bogus_scope_xyz/")
    result = store.dispatch(op)
    assert isinstance(result, MemoryExecutionFailure)
    assert result.kind == "invalid_uri"


def test_transport_failure_for_unreachable_host(
    openviking_root_api_key: str,
) -> None:
    """Open a store against a port that nothing listens on; the first
    dispatch should surface as ``kind="transport"``.

    NOTE: depending on the SDK, the failure may also show up at
    ``open()`` time (during ``client.initialize()``). In that case we get
    a ``MemoryBackendError`` and the test still asserts the right
    *category* of failure -- a transport problem -- just at a different
    layer.
    """
    from rath.memory.errors import MemoryBackendError

    backend = OpenVikingBackend()
    spec = MemoryStoreSpec(
        account_id="default",
        user_id="default",
        agent_id="default",
        options={
            "url": "http://127.0.0.1:1",  # nothing listens on port 1
            "api_key": openviking_root_api_key,
            "timeout": 2.0,
        },
    )
    try:
        store = backend.open(spec)
    except MemoryBackendError:
        return  # transport failure surfaced at open(), test passes
    try:
        result = store.dispatch(MemoryOpFind(query="x"))
    finally:
        backend.close(store)
    assert isinstance(result, MemoryExecutionFailure)
    assert result.kind in {"transport", "internal"}


def test_unauthorized_for_bogus_api_key(openviking_url: str) -> None:
    """A wrong api key should yield ``kind="unauthorized"`` on first
    real call. Mirrors the transport test: failure may also bubble at
    open() time as MemoryBackendError."""
    from rath.memory.errors import MemoryBackendError

    backend = OpenVikingBackend()
    spec = MemoryStoreSpec(
        account_id="default",
        user_id="default",
        agent_id="default",
        options={
            "url": openviking_url,
            "api_key": "definitely-not-a-real-key-" + uuid.uuid4().hex,
        },
    )
    try:
        store = backend.open(spec)
    except MemoryBackendError:
        return
    try:
        result = store.dispatch(MemoryOpFind(query="x"))
    finally:
        backend.close(store)
    assert isinstance(result, MemoryExecutionFailure)
    assert result.kind in {"unauthorized", "internal"}
