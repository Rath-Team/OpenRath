"""Refcount + lifecycle semantics for :class:`rath.memory.abc.MemoryStore`."""

from __future__ import annotations

import pytest

from rath.memory.abc import MemoryStore, MemoryStoreSpec
from rath.memory.errors import MemoryStoreClosed


class _FakeBackend:
    """Minimal stand-in for :class:`MemoryBackend` (which lands in Task 1.5).

    Only ``close`` is exercised by :class:`MemoryStore` here.
    """

    def __init__(self) -> None:
        self.close_calls: list[MemoryStore] = []

    def close(self, store: MemoryStore) -> None:
        self.close_calls.append(store)
        store.closed = True


def _make_store(backend: _FakeBackend | None = None) -> MemoryStore:
    be = backend if backend is not None else _FakeBackend()
    # ``backend`` is typed as ``MemoryBackend`` but the dataclass accepts any
    # object that quacks like one for the purposes of refcount mechanics.
    return MemoryStore(backend=be, handle="h1")  # type: ignore[arg-type]


def test_fresh_store_has_zero_refcount():
    store = _make_store()
    assert store.refcount == 0
    assert store.closed is False


def test_acquire_increments_refcount_and_returns_self():
    store = _make_store()
    out = store.acquire()
    assert out is store
    assert store.refcount == 1


def test_release_at_one_calls_backend_close_exactly_once():
    fake = _FakeBackend()
    store = _make_store(fake)
    store.acquire()
    store.release()
    assert fake.close_calls == [store]
    assert store.closed is True


def test_release_after_close_is_noop():
    fake = _FakeBackend()
    store = _make_store(fake)
    store.acquire()
    store.release()
    # Second release after close: no extra backend.close.
    store.release()
    assert fake.close_calls == [store]


def test_context_manager_acquires_then_releases():
    fake = _FakeBackend()
    store = _make_store(fake)
    with store as s:
        assert s is store
        assert store.refcount == 1
    assert store.refcount == 0
    assert fake.close_calls == [store]
    assert store.closed is True


def test_nested_context_manager_tracks_refcount():
    fake = _FakeBackend()
    store = _make_store(fake)
    with store:
        with store:
            assert store.refcount == 2
        # Inner exit decrements but does NOT close (refcount still 1).
        assert store.refcount == 1
        assert fake.close_calls == []
    assert store.refcount == 0
    assert fake.close_calls == [store]


def test_acquire_after_close_raises_memory_store_closed():
    fake = _FakeBackend()
    store = _make_store(fake)
    store.acquire()
    store.release()
    assert store.closed is True
    with pytest.raises(MemoryStoreClosed):
        store.acquire()


def test_memory_store_spec_defaults_are_all_none():
    spec = MemoryStoreSpec()
    assert spec.namespace is None
    assert spec.account_id is None
    assert spec.user_id is None
    assert spec.agent_id is None
    assert spec.options is None


def test_memory_store_spec_carries_namespace_and_options():
    spec = MemoryStoreSpec(
        namespace="proj-a",
        account_id="acct",
        user_id="u1",
        agent_id="agent-7",
        options={"endpoint": "https://example"},
    )
    assert spec.namespace == "proj-a"
    assert spec.account_id == "acct"
    assert spec.user_id == "u1"
    assert spec.agent_id == "agent-7"
    assert spec.options == {"endpoint": "https://example"}


def test_store_dispatch_after_close_raises():
    fake = _FakeBackend()
    store = _make_store(fake)
    store.acquire()
    store.release()
    with pytest.raises(MemoryStoreClosed):
        store.acquire()
