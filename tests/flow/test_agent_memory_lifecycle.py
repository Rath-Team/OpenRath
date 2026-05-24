"""``Agent.close()`` releases the bound memory store; context-manager support."""

from __future__ import annotations

from dataclasses import dataclass, field

from rath.flow.agent import Agent
from rath.memory.abc import MemoryBackend, MemoryStore, MemoryStoreSpec
from rath.memory.capabilities import MemoryCapabilities, ScopeModel
from rath.memory.op_types import MemoryOp
from rath.memory.results import MemoryResult


@dataclass
class _FakeBackend(MemoryBackend):
    close_calls: list[str] = field(default_factory=list)

    @classmethod
    def is_available(cls) -> bool:
        return True

    @classmethod
    def capabilities(cls) -> MemoryCapabilities:
        return MemoryCapabilities(
            scope_model=ScopeModel.HYBRID,
            supports_write=False,
            supports_read=False,
            supports_list=False,
            supports_tree=False,
            supports_vector_search=False,
            supports_intent_search=False,
            supports_resource_ingest=False,
            supports_session_commit=False,
            supports_l0_l1_l2=False,
        )

    @classmethod
    def supported_ops(cls) -> frozenset[type[MemoryOp]]:
        return frozenset()

    def store_count(self) -> int:
        return 1

    def open(self, spec: MemoryStoreSpec | None = None) -> MemoryStore:
        return MemoryStore(backend=self, handle="lc", spec=spec or MemoryStoreSpec())

    def close(self, store: MemoryStore) -> None:
        if not store.closed:
            self.close_calls.append(store.handle)
        store.closed = True

    def dispatch(
        self, store: MemoryStore, op: MemoryOp
    ) -> MemoryResult:  # pragma: no cover
        raise NotImplementedError


def test_close_decrements_refcount_and_closes_at_zero() -> None:
    backend = _FakeBackend()
    store = backend.open()
    agent = Agent("system", model="gpt-5.5", memory=store)
    assert store.refcount == 1
    agent.close()
    assert store.closed
    assert backend.close_calls == ["lc"]


def test_close_with_shared_store_does_not_close_backend_until_refcount_zero() -> None:
    backend = _FakeBackend()
    store = backend.open()
    store.acquire()  # external holder
    assert store.refcount == 1
    agent = Agent("system", model="gpt-5.5", memory=store)
    assert store.refcount == 2
    agent.close()
    assert not store.closed
    assert store.refcount == 1
    assert backend.close_calls == []


def test_close_is_idempotent() -> None:
    backend = _FakeBackend()
    store = backend.open()
    agent = Agent("system", model="gpt-5.5", memory=store)
    agent.close()
    agent.close()
    assert backend.close_calls == ["lc"]


def test_close_with_no_memory_is_noop() -> None:
    agent = Agent("system", model="gpt-5.5")
    agent.close()  # must not raise
    agent.close()


def test_context_manager_releases_on_exit() -> None:
    backend = _FakeBackend()
    store = backend.open()
    with Agent("system", model="gpt-5.5", memory=store) as agent:
        assert store.refcount == 1
        assert agent.memory is store
    assert store.closed
    assert backend.close_calls == ["lc"]
