"""ABC contract + unsupported-op handling for :class:`rath.memory.abc.MemoryBackend`."""

from __future__ import annotations

import pytest

from rath.memory.abc import MemoryBackend, MemoryStore, MemoryStoreSpec
from rath.memory.capabilities import MemoryCapabilities, ScopeModel
from rath.memory.errors import UnsupportedMemoryOp
from rath.memory.op_types import (
    MemoryOp,
    MemoryOpCommit,
    MemoryOpFind,
)
from rath.memory.results import MemoryFindResult, MemoryHit

_CAPS = MemoryCapabilities(
    scope_model=ScopeModel.KV,
    supports_write=False,
    supports_read=False,
    supports_list=False,
    supports_tree=False,
    supports_vector_search=True,
    supports_intent_search=False,
    supports_resource_ingest=False,
    supports_session_commit=False,
    supports_l0_l1_l2=False,
)


class TinyBackend(MemoryBackend):
    """Minimal concrete backend used to exercise the ABC contract."""

    name = "tiny"

    def __init__(self) -> None:
        self._opened: list[MemoryStore] = []
        self._closed: list[MemoryStore] = []

    @classmethod
    def is_available(cls) -> bool:
        return True

    @classmethod
    def capabilities(cls) -> MemoryCapabilities:
        return _CAPS

    @classmethod
    def supported_ops(cls) -> frozenset[type[MemoryOp]]:
        return frozenset({MemoryOpFind})

    def store_count(self) -> int:
        return len(self._opened) - len(self._closed)

    def open(self, spec: MemoryStoreSpec | None = None) -> MemoryStore:
        store = MemoryStore(backend=self, handle=f"tiny-{len(self._opened)}", spec=spec)
        self._opened.append(store)
        return store

    def close(self, store: MemoryStore) -> None:
        if store.closed:
            return
        store.closed = True
        self._closed.append(store)

    def dispatch(self, store: MemoryStore, op: MemoryOp) -> MemoryFindResult:
        if type(op) not in self.supported_ops():
            raise UnsupportedMemoryOp(type(op), self.name)
        assert isinstance(op, MemoryOpFind)
        return MemoryFindResult(hits=(MemoryHit(uri=f"tiny://{op.query}", score=1.0),))


def test_abstract_subclass_missing_methods_cannot_instantiate():
    class Broken(MemoryBackend):
        name = "broken"

    with pytest.raises(TypeError):
        Broken()  # type: ignore[abstract]


def test_concrete_backend_instantiates_and_reports_capabilities():
    backend = TinyBackend()
    assert backend.store_count() == 0
    assert TinyBackend.is_available() is True
    assert TinyBackend.capabilities().scope_model is ScopeModel.KV
    assert MemoryOpFind in TinyBackend.supported_ops()


def test_dispatch_supported_op_returns_typed_result():
    backend = TinyBackend()
    store = backend.open()
    result = backend.dispatch(store, MemoryOpFind(query="hello"))
    assert isinstance(result, MemoryFindResult)
    assert result.hits[0].uri == "tiny://hello"


def test_dispatch_unsupported_op_raises_unsupported_memory_op():
    backend = TinyBackend()
    store = backend.open()
    op = MemoryOpCommit(session_id="s1", messages=())
    with pytest.raises(UnsupportedMemoryOp) as ei:
        backend.dispatch(store, op)
    assert ei.value.op_type is MemoryOpCommit
    assert ei.value.backend_name == "tiny"


def test_open_and_close_track_store_count():
    backend = TinyBackend()
    s1 = backend.open()
    s2 = backend.open()
    assert backend.store_count() == 2
    backend.close(s1)
    assert backend.store_count() == 1
    backend.close(s2)
    assert backend.store_count() == 0


def test_close_is_idempotent():
    backend = TinyBackend()
    store = backend.open()
    backend.close(store)
    backend.close(store)
    assert backend.store_count() == 0
