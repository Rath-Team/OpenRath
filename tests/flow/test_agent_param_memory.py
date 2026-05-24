"""``AgentParam`` carries an optional :class:`MemoryStore` field.

Backward compatibility: the existing two-positional-arg form
(``AgentParam(agent_session, provider)``) keeps working and surfaces
``memory is None``.
"""

from __future__ import annotations

from rath.flow.agent_param import AgentParam, Provider
from rath.memory.abc import MemoryBackend, MemoryStore, MemoryStoreSpec
from rath.memory.capabilities import MemoryCapabilities, ScopeModel
from rath.memory.op_types import MemoryOp
from rath.memory.results import MemoryResult
from rath.session.session import Session


class _NullBackend(MemoryBackend):
    """Minimal in-test backend that ``open()`` can return a store from."""

    _caps = MemoryCapabilities(
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

    def __init__(self) -> None:
        self._n = 0

    @classmethod
    def is_available(cls) -> bool:
        return True

    @classmethod
    def capabilities(cls) -> MemoryCapabilities:
        return cls._caps

    @classmethod
    def supported_ops(cls) -> frozenset[type[MemoryOp]]:
        return frozenset()

    def store_count(self) -> int:
        return self._n

    def open(self, spec: MemoryStoreSpec | None = None) -> MemoryStore:
        self._n += 1
        return MemoryStore(
            backend=self, handle=f"h{self._n}", spec=spec or MemoryStoreSpec()
        )

    def close(self, store: MemoryStore) -> None:
        if not store.closed:
            self._n -= 1
        store.closed = True

    def dispatch(
        self, store: MemoryStore, op: MemoryOp
    ) -> MemoryResult:  # pragma: no cover -- unused
        raise NotImplementedError


def test_agent_param_default_memory_is_none() -> None:
    sess = Session.from_agent_prompt("system")
    param = AgentParam(sess, Provider())
    assert param.memory is None


def test_agent_param_carries_memory_store() -> None:
    sess = Session.from_agent_prompt("system")
    store = _NullBackend().open()
    param = AgentParam(sess, Provider(), memory=store)
    assert param.memory is store


def test_agent_param_repr_includes_memory_line_when_set() -> None:
    sess = Session.from_agent_prompt("system")
    store = _NullBackend().open()
    param = AgentParam(sess, Provider(), memory=store)
    rep = repr(param)
    assert "(memory)" in rep


def test_agent_param_repr_omits_memory_line_when_none() -> None:
    sess = Session.from_agent_prompt("system")
    param = AgentParam(sess, Provider())
    rep = repr(param)
    assert "(memory)" not in rep


def test_agent_param_data_includes_memory_key() -> None:
    sess = Session.from_agent_prompt("system")
    store = _NullBackend().open()
    param = AgentParam(sess, Provider(), memory=store)
    assert param.data["memory"] is store
    none_param = AgentParam(sess, Provider())
    assert none_param.data["memory"] is None
