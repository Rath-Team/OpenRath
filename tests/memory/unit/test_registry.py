"""Registry semantics for :mod:`rath.memory.registry`."""

from __future__ import annotations

import pytest

from rath.memory import registry as memreg
from rath.memory.abc import MemoryBackend, MemoryStore, MemoryStoreSpec
from rath.memory.capabilities import MemoryCapabilities, ScopeModel
from rath.memory.errors import MemoryBackendNotFound
from rath.memory.op_types import MemoryOp
from rath.memory.results import MemoryResult

_CAPS = MemoryCapabilities(
    scope_model=ScopeModel.KV,
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


def _make_backend(*, available: bool = True) -> type[MemoryBackend]:
    """Build a fresh anonymous backend class so each test gets a clean type."""

    class _Backend(MemoryBackend):
        @classmethod
        def is_available(cls) -> bool:
            return available

        @classmethod
        def capabilities(cls) -> MemoryCapabilities:
            return _CAPS

        @classmethod
        def supported_ops(cls) -> frozenset[type[MemoryOp]]:
            return frozenset()

        def store_count(self) -> int:
            return 0

        def open(self, spec: MemoryStoreSpec | None = None) -> MemoryStore:
            return MemoryStore(backend=self, handle="h")

        def close(self, store: MemoryStore) -> None:
            store.closed = True

        def dispatch(self, store: MemoryStore, op: MemoryOp) -> MemoryResult:
            raise NotImplementedError

    return _Backend


def test_register_then_get_returns_fresh_instance(clean_memory_registry):
    cls = memreg.register("alpha")(_make_backend())
    inst = memreg.get("alpha")
    assert isinstance(inst, cls)
    assert cls.name == "alpha"
    # Two get() calls produce distinct instances.
    assert memreg.get("alpha") is not inst


def test_get_class_returns_class_without_instantiating(clean_memory_registry):
    cls = memreg.register("beta")(_make_backend())
    assert memreg.get_class("beta") is cls


def test_duplicate_registration_raises(clean_memory_registry):
    memreg.register("gamma")(_make_backend())
    with pytest.raises(ValueError, match="gamma"):
        memreg.register("gamma")(_make_backend())


def test_get_unknown_raises_memory_backend_not_found(clean_memory_registry):
    with pytest.raises(MemoryBackendNotFound) as ei:
        memreg.get("nope")
    assert ei.value.name == "nope"
    assert ei.value.available == []


def test_preferred_picks_first_available(clean_memory_registry):
    memreg.register("a")(_make_backend(available=False))
    cls_b = memreg.register("b")(_make_backend(available=True))
    memreg.register("c")(_make_backend(available=True))
    inst = memreg.preferred(["a", "b", "c"])
    assert isinstance(inst, cls_b)


def test_preferred_none_available_raises(clean_memory_registry):
    memreg.register("a")(_make_backend(available=False))
    with pytest.raises(MemoryBackendNotFound):
        memreg.preferred(["a", "missing"])


def test_set_default_then_current_returns_instance(clean_memory_registry):
    cls = memreg.register("d")(_make_backend())
    memreg.set_default("d")
    inst = memreg.current()
    assert isinstance(inst, cls)


def test_current_without_default_raises(clean_memory_registry):
    with pytest.raises(MemoryBackendNotFound):
        memreg.current()


def test_set_default_unknown_raises(clean_memory_registry):
    with pytest.raises(MemoryBackendNotFound):
        memreg.set_default("ghost")


def test_list_names_preserves_insertion_order(clean_memory_registry):
    memreg.register("first")(_make_backend())
    memreg.register("second")(_make_backend())
    memreg.register("third")(_make_backend())
    assert memreg.list_names() == ["first", "second", "third"]


def test_is_available_reflects_class_method(clean_memory_registry):
    memreg.register("on")(_make_backend(available=True))
    memreg.register("off")(_make_backend(available=False))
    assert memreg.is_available("on") is True
    assert memreg.is_available("off") is False
    assert memreg.is_available("missing") is False
