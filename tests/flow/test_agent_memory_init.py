"""``Agent.__init__`` accepts ``memory=`` in three forms.

Forms covered by ``_resolve_memory(memory)`` inside ``Agent.__init__``:

1. An already-open ``MemoryStore`` -> bound directly (refcount +1 via ``acquire``).
2. A backend registry name (str) -> resolved through ``rath.memory.get(name).open()``.
3. A :class:`MemoryStoreSpec` -> resolved through the configured default backend
   (``rath.memory.current()``); raises ``MemoryBackendNotFound`` if unset.

``memory=None`` is the legacy form and remains the default.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

import rath.memory.registry as _registry
from rath.flow.agent import Agent
from rath.memory.abc import MemoryBackend, MemoryStore, MemoryStoreSpec
from rath.memory.capabilities import MemoryCapabilities, ScopeModel
from rath.memory.errors import MemoryBackendNotFound
from rath.memory.op_types import MemoryOp
from rath.memory.registry import register
from rath.memory.results import MemoryResult


@pytest.fixture(autouse=True)
def _reset_memory_registry():
    saved_reg = dict(_registry._REGISTRY)
    saved_default = dict(_registry._DEFAULT)
    _registry._REGISTRY.clear()
    _registry._DEFAULT.clear()
    yield
    _registry._REGISTRY.clear()
    _registry._REGISTRY.update(saved_reg)
    _registry._DEFAULT.clear()
    _registry._DEFAULT.update(saved_default)


@dataclass
class _FakeBackend(MemoryBackend):
    opened: list[MemoryStore] = field(default_factory=list)
    closed_handles: list[str] = field(default_factory=list)

    @classmethod
    def is_available(cls) -> bool:
        return True

    @classmethod
    def capabilities(cls) -> MemoryCapabilities:
        return MemoryCapabilities(
            scope_model=ScopeModel.HYBRID,
            supports_write=True,
            supports_read=True,
            supports_list=True,
            supports_tree=False,
            supports_vector_search=True,
            supports_intent_search=False,
            supports_resource_ingest=False,
            supports_session_commit=False,
            supports_l0_l1_l2=False,
        )

    @classmethod
    def supported_ops(cls) -> frozenset[type[MemoryOp]]:
        return frozenset()

    def store_count(self) -> int:
        return len(self.opened) - len(self.closed_handles)

    def open(self, spec: MemoryStoreSpec | None = None) -> MemoryStore:
        handle = f"h{len(self.opened)}"
        s = MemoryStore(backend=self, handle=handle, spec=spec or MemoryStoreSpec())
        self.opened.append(s)
        return s

    def close(self, store: MemoryStore) -> None:
        if not store.closed:
            self.closed_handles.append(store.handle)
        store.closed = True

    def dispatch(
        self, store: MemoryStore, op: MemoryOp
    ) -> MemoryResult:  # pragma: no cover
        raise NotImplementedError


def test_agent_without_memory_keeps_legacy_behaviour() -> None:
    a = Agent("system", model="gpt-5.5")
    assert a.memory is None
    assert a.agent.memory is None


def test_agent_accepts_existing_memory_store_and_acquires_refcount() -> None:
    backend = _FakeBackend()
    store = backend.open()
    assert store.refcount == 0
    a = Agent("system", model="gpt-5.5", memory=store)
    assert a.memory is store
    assert a.agent.memory is store
    assert store.refcount == 1


def test_agent_accepts_backend_name_and_opens_fresh_store() -> None:
    register("fake_named")(_FakeBackend)
    a = Agent("system", model="gpt-5.5", memory="fake_named")
    assert isinstance(a.memory, MemoryStore)
    assert a.memory.refcount == 1
    assert a.memory.backend.store_count() == 1


def test_agent_accepts_spec_via_default_backend() -> None:
    register("fake_default")(_FakeBackend)
    _registry.set_default("fake_default")
    spec = MemoryStoreSpec(account_id="acc", user_id="u", agent_id="ag")
    a = Agent("system", model="gpt-5.5", memory=spec)
    assert isinstance(a.memory, MemoryStore)
    assert a.memory.spec is spec
    assert a.memory.refcount == 1


def test_agent_with_spec_but_no_default_raises_not_found() -> None:
    spec = MemoryStoreSpec(account_id="acc")
    with pytest.raises(MemoryBackendNotFound):
        Agent("system", model="gpt-5.5", memory=spec)


def test_agent_with_unknown_backend_name_raises_not_found() -> None:
    with pytest.raises(MemoryBackendNotFound):
        Agent("system", model="gpt-5.5", memory="not_a_real_backend")
