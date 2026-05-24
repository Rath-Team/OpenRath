"""``Agent.remember`` / ``Agent.recall`` / ``Agent.commit`` public methods."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from rath.flow.agent import Agent
from rath.memory.abc import MemoryBackend, MemoryStore, MemoryStoreSpec
from rath.memory.capabilities import MemoryCapabilities, ScopeModel
from rath.memory.op_types import (
    MemoryOp,
    MemoryOpCommit,
    MemoryOpFind,
    MemoryOpWrite,
)
from rath.memory.results import (
    MemoryCommitResult,
    MemoryFindResult,
    MemoryHit,
    MemoryResult,
    MemoryWriteResult,
)
from rath.session import Session


@dataclass
class _FakeBackend(MemoryBackend):
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
            supports_intent_search=False,
            supports_resource_ingest=False,
            supports_session_commit=True,
            supports_l0_l1_l2=True,
        )

    @classmethod
    def supported_ops(cls) -> frozenset[type[MemoryOp]]:
        return frozenset({MemoryOpWrite, MemoryOpFind, MemoryOpCommit})

    def store_count(self) -> int:
        return 1

    def open(self, spec: MemoryStoreSpec | None = None) -> MemoryStore:
        return MemoryStore(backend=self, handle="fake", spec=spec or MemoryStoreSpec())

    def close(self, store: MemoryStore) -> None:
        store.closed = True

    def dispatch(self, store: MemoryStore, op: MemoryOp) -> MemoryResult:
        self.ops_seen.append(op)
        if isinstance(op, MemoryOpWrite):
            return MemoryWriteResult(
                uri=op.uri, bytes_written=len(op.content.encode("utf-8"))
            )
        if isinstance(op, MemoryOpFind):
            return MemoryFindResult(
                hits=(MemoryHit(uri="viking://user/m/x", score=0.5, snippet="hit"),)
            )
        if isinstance(op, MemoryOpCommit):
            return MemoryCommitResult(
                task_id="t", archived_uri="viking://session/s/", extracted_count=-1
            )
        raise NotImplementedError


def _agent_with_memory() -> tuple[Agent, _FakeBackend]:
    backend = _FakeBackend()
    store = backend.open()
    agent = Agent("system", model="gpt-5.5", memory=store)
    return agent, backend


def test_remember_dispatches_write_under_user_memories() -> None:
    agent, backend = _agent_with_memory()
    result = agent.remember("I prefer dark mode")
    assert isinstance(result, MemoryWriteResult)
    write = next(op for op in backend.ops_seen if isinstance(op, MemoryOpWrite))
    assert write.uri.startswith("viking://user/memories/")
    assert write.content == "I prefer dark mode"


def test_remember_with_agent_scope_uses_agent_namespace() -> None:
    agent, backend = _agent_with_memory()
    agent.remember("call tool first", scope="agent", category="tools")
    write = next(op for op in backend.ops_seen if isinstance(op, MemoryOpWrite))
    assert write.uri.startswith("viking://agent/memories/tools/")


def test_recall_dispatches_find() -> None:
    agent, backend = _agent_with_memory()
    result = agent.recall("dark mode", top_k=3)
    assert isinstance(result, MemoryFindResult)
    find = next(op for op in backend.ops_seen if isinstance(op, MemoryOpFind))
    assert find.query == "dark mode"
    assert find.top_k == 3


def test_commit_dispatches_with_session_id_and_messages() -> None:
    agent, backend = _agent_with_memory()
    sess = Session.from_user_message("hello")
    result = agent.commit(sess, wait=True)
    assert isinstance(result, MemoryCommitResult)
    commit = next(op for op in backend.ops_seen if isinstance(op, MemoryOpCommit))
    assert commit.session_id == str(sess.id)
    assert commit.messages
    assert commit.wait is True


def test_public_api_raises_when_no_memory_store() -> None:
    agent = Agent("system", model="gpt-5.5")
    sess = Session.from_user_message("hello")
    with pytest.raises(RuntimeError, match="no memory"):
        agent.remember("x")
    with pytest.raises(RuntimeError, match="no memory"):
        agent.recall("x")
    with pytest.raises(RuntimeError, match="no memory"):
        agent.commit(sess)
