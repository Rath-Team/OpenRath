"""Memory injection policy + ``DefaultRecallInjection``.

We avoid any live LLM: the store is a tiny scripted fake that records
which ops it sees and replies with a fixed :class:`MemoryFindResult`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pytest

from rath.flow.memory_inject import DefaultRecallInjection, MemoryInjectionPolicy
from rath.memory.abc import MemoryBackend, MemoryStore, MemoryStoreSpec
from rath.memory.capabilities import MemoryCapabilities, ScopeModel
from rath.memory.op_types import MemoryOp, MemoryOpFind
from rath.memory.results import MemoryFindResult, MemoryHit, MemoryResult
from rath.session.chunk import ChunkKind, ChunkTable, user_text_chunk
from rath.session.session import Session


@dataclass
class _FakeBackend(MemoryBackend):
    hits: tuple[MemoryHit, ...] = ()
    ops_seen: list[MemoryOp] = field(default_factory=list)

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
            supports_intent_search=True,
            supports_resource_ingest=False,
            supports_session_commit=True,
            supports_l0_l1_l2=True,
        )

    @classmethod
    def supported_ops(cls) -> frozenset[type[MemoryOp]]:
        return frozenset({MemoryOpFind})

    def store_count(self) -> int:
        return 1

    def open(self, spec: MemoryStoreSpec | None = None) -> MemoryStore:
        return MemoryStore(backend=self, handle="fake", spec=spec or MemoryStoreSpec())

    def close(self, store: MemoryStore) -> None:
        store.closed = True

    def dispatch(self, store: MemoryStore, op: MemoryOp) -> MemoryResult:
        self.ops_seen.append(op)
        if isinstance(op, MemoryOpFind):
            return MemoryFindResult(hits=self.hits)
        raise NotImplementedError(f"fake backend does not handle {type(op).__name__}")


def _user_session(*user_msgs: str) -> Session:
    sess = Session.from_agent_prompt("system")
    appended = sess.chunk_table.rows + tuple(user_text_chunk(m) for m in user_msgs)
    sess.chunk_table = ChunkTable(rows=appended)
    return sess


def test_default_recall_injection_runtime_checkable() -> None:
    assert isinstance(DefaultRecallInjection(), MemoryInjectionPolicy)


def test_default_recall_emits_one_chunk_per_hit() -> None:
    backend = _FakeBackend(
        hits=(
            MemoryHit(
                uri="viking://user/m/a",
                score=0.9,
                snippet="dark mode preferred",
                level="abstract",
            ),
            MemoryHit(
                uri="viking://user/m/b",
                score=0.8,
                snippet="GMT+8 timezone",
                level="abstract",
            ),
        ),
    )
    store = backend.open()
    sess = _user_session("Do you remember my preferences?")
    policy = DefaultRecallInjection(
        top_k=2, target_uri="viking://user/memories/", level="abstract"
    )
    chunks = policy.inject(sess, store)
    assert isinstance(chunks, tuple)
    assert len(chunks) == 2
    for chunk in chunks:
        assert chunk.kind == ChunkKind.SYSTEM
        assert "content" in chunk.payload
    bodies = "\n".join(c.payload["content"] for c in chunks)
    assert "dark mode preferred" in bodies
    assert "GMT+8 timezone" in bodies
    # The dispatch should carry the configured target_uri + top_k
    assert backend.ops_seen, "policy should issue at least one find op"
    op = backend.ops_seen[-1]
    assert isinstance(op, MemoryOpFind)
    assert op.top_k == 2
    assert op.target_uri == "viking://user/memories/"


def test_default_recall_returns_empty_when_no_user_messages() -> None:
    backend = _FakeBackend(hits=(MemoryHit(uri="x", score=1.0, snippet="x"),))
    store = backend.open()
    sess = Session.from_agent_prompt("system only -- no user turn")
    policy = DefaultRecallInjection()
    assert policy.inject(sess, store) == ()
    assert backend.ops_seen == [], "no dispatch on empty user history"


def test_default_recall_returns_empty_on_closed_store_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    backend = _FakeBackend(hits=())
    store = backend.open()
    backend.close(store)
    assert store.closed
    sess = _user_session("hello")
    policy = DefaultRecallInjection()
    with caplog.at_level(logging.WARNING):
        result = policy.inject(sess, store)
    assert result == ()
    assert any("memory" in rec.getMessage().lower() for rec in caplog.records)


def test_default_recall_returns_empty_when_store_yields_no_hits() -> None:
    backend = _FakeBackend(hits=())
    store = backend.open()
    sess = _user_session("anything")
    policy = DefaultRecallInjection()
    assert policy.inject(sess, store) == ()
