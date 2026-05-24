"""Lifecycle (open/close/store_count) tests for :class:`OpenVikingBackend`.

These run against the **real** OpenViking server started by
``scripts/launch_openviking.sh``; the autouse ``_openviking_canary``
fixture in this directory's conftest skips the module otherwise.

The embedded mode (``OpenViking(path=...)``) requires the ``pyagfs``
binding-client wheel and is exercised conditionally — see the test
docstring below.
"""

from __future__ import annotations

import pytest

from rath.memory import MemoryStore, MemoryStoreSpec
from rath.memory.adapters.openviking import OpenVikingBackend

pytestmark = pytest.mark.openviking


@pytest.fixture
def http_spec(openviking_url: str, openviking_root_api_key: str) -> MemoryStoreSpec:
    return MemoryStoreSpec(
        namespace="user",
        account_id="default",
        user_id="default",
        agent_id="default",
        options={"url": openviking_url, "api_key": openviking_root_api_key},
    )


def test_open_returns_memory_store_handle(http_spec: MemoryStoreSpec) -> None:
    backend = OpenVikingBackend()
    try:
        store = backend.open(http_spec)
        assert isinstance(store, MemoryStore)
        assert store.handle  # non-empty
        assert store.spec is http_spec
        assert store.closed is False
        assert backend.store_count() == 1
    finally:
        backend.close(store)


def test_store_count_tracks_multiple_opens(http_spec: MemoryStoreSpec) -> None:
    backend = OpenVikingBackend()
    s1 = backend.open(http_spec)
    s2 = backend.open(http_spec)
    try:
        assert s1.handle != s2.handle
        assert backend.store_count() == 2
    finally:
        backend.close(s1)
        backend.close(s2)
    assert backend.store_count() == 0


def test_close_marks_store_closed_and_decrements_count(
    http_spec: MemoryStoreSpec,
) -> None:
    backend = OpenVikingBackend()
    store = backend.open(http_spec)
    assert backend.store_count() == 1
    backend.close(store)
    assert store.closed is True
    assert backend.store_count() == 0


def test_close_is_idempotent(http_spec: MemoryStoreSpec) -> None:
    backend = OpenVikingBackend()
    store = backend.open(http_spec)
    backend.close(store)
    backend.close(store)  # second call must not raise
    assert store.closed is True
    assert backend.store_count() == 0


def test_open_embedded_mode_or_skip(tmp_path) -> None:
    """Exercise embedded mode if the ``pyagfs`` binding-client is available.

    The embedded backend (`openviking.OpenViking(path=...)`) needs a
    platform-specific Go binding wheel. When that wheel is absent the
    constructor raises ImportError -- the adapter is required to surface
    that as ``MemoryBackendError`` ("openviking embedded mode requires
    pyagfs binding-client"), which this test catches and converts to a
    SKIP. We do **not** mock around the missing wheel: if the platform
    can't run embedded, that's the user's environment, not our problem.
    """
    from rath.memory.errors import MemoryBackendError

    spec = MemoryStoreSpec(options={"path": str(tmp_path / "ov_embedded")})
    backend = OpenVikingBackend()
    try:
        store = backend.open(spec)
    except MemoryBackendError as exc:
        pytest.skip(f"embedded mode unavailable: {exc}")
    try:
        assert isinstance(store, MemoryStore)
        assert backend.store_count() == 1
    finally:
        backend.close(store)
