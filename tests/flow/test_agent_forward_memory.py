"""``Agent.forward`` injects memory chunks and optionally commits.

Uses :class:`ScriptedSessionLoopExecutor` (no live LLM) plus a fake
in-process backend that records every op it sees. The fake exposes the
exact same surface the live OpenViking adapter does for the small
subset Agent uses (``MemoryOpFind`` and ``MemoryOpCommit``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from rath.flow.agent import Agent
from rath.flow.memory_inject import DefaultRecallInjection
from rath.llm import RathLLMAssistantMessage, RathLLMChatChoice, RathLLMChatResponse
from rath.memory.abc import MemoryBackend, MemoryStore, MemoryStoreSpec
from rath.memory.capabilities import MemoryCapabilities, ScopeModel
from rath.memory.op_types import MemoryOp, MemoryOpCommit, MemoryOpFind
from rath.memory.results import (
    MemoryCommitResult,
    MemoryFindResult,
    MemoryHit,
    MemoryResult,
)
from rath.session import Session, session_registry
from rath.session.chunk import ChunkKind
from tests.session.scripted_loop_executor import ScriptedSessionLoopExecutor


@pytest.fixture(autouse=True)
def _clear_active_session_registry() -> None:
    yield
    session_registry().set_active(None)


@dataclass
class _FakeBackend(MemoryBackend):
    find_hits: tuple[MemoryHit, ...] = ()
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
            supports_tree=True,
            supports_vector_search=True,
            supports_intent_search=True,
            supports_resource_ingest=True,
            supports_session_commit=True,
            supports_l0_l1_l2=True,
        )

    @classmethod
    def supported_ops(cls) -> frozenset[type[MemoryOp]]:
        return frozenset({MemoryOpFind, MemoryOpCommit})

    def store_count(self) -> int:
        return 1

    def open(self, spec: MemoryStoreSpec | None = None) -> MemoryStore:
        return MemoryStore(backend=self, handle="fake", spec=spec or MemoryStoreSpec())

    def close(self, store: MemoryStore) -> None:
        store.closed = True

    def dispatch(self, store: MemoryStore, op: MemoryOp) -> MemoryResult:
        self.ops_seen.append(op)
        if isinstance(op, MemoryOpFind):
            return MemoryFindResult(hits=self.find_hits)
        if isinstance(op, MemoryOpCommit):
            return MemoryCommitResult(
                task_id="task-x", archived_uri="viking://session/s/", extracted_count=-1
            )
        raise NotImplementedError(f"fake: no handler for {type(op).__name__}")


def _scripted_response(text: str) -> RathLLMChatResponse:
    return RathLLMChatResponse(
        id="chatcmpl-test",
        choices=(
            RathLLMChatChoice(
                index=0,
                message=RathLLMAssistantMessage(content=text),
                finish_reason="stop",
            ),
        ),
        created=1,
        model="script",
    )


def test_forward_without_memory_is_unchanged() -> None:
    exec_ = ScriptedSessionLoopExecutor([_scripted_response("ok")])
    agent = Agent("system", model="gpt-5.5")
    agent._executor_override = exec_  # tests-only hook (set below in agent.py)
    sess = Session.from_user_message("hi")
    out = agent.forward(sess)
    kinds = [row.kind for row in out.chunk_table.rows]
    # With no memory, no SYSTEM chunks should be injected into the user transcript.
    assert ChunkKind.SYSTEM not in kinds
    assert kinds[-1] == ChunkKind.ASSISTANT


def test_forward_prepends_injected_system_chunks() -> None:
    backend = _FakeBackend(
        find_hits=(
            MemoryHit(
                uri="viking://user/m/1",
                score=0.9,
                snippet="loves dark mode",
                level="abstract",
            ),
        ),
    )
    store = backend.open()
    exec_ = ScriptedSessionLoopExecutor([_scripted_response("noted")])
    agent = Agent(
        "system",
        model="gpt-5.5",
        memory=store,
        memory_inject=DefaultRecallInjection(
            top_k=1, target_uri="viking://user/memories/"
        ),
    )
    agent._executor_override = exec_
    sess = Session.from_user_message("Hello, do you remember me?")
    out = agent.forward(sess)
    # Exactly one MemoryOpFind dispatched, no commit.
    assert any(isinstance(op, MemoryOpFind) for op in backend.ops_seen)
    assert not any(isinstance(op, MemoryOpCommit) for op in backend.ops_seen)
    # The injected snippet should appear as a system chunk in the output.
    sys_bodies = "\n".join(
        str(r.payload.get("content", ""))
        for r in out.chunk_table.rows
        if r.kind == ChunkKind.SYSTEM
    )
    assert "loves dark mode" in sys_bodies


def test_forward_with_commit_on_forward_dispatches_one_commit() -> None:
    backend = _FakeBackend(find_hits=())
    store = backend.open()
    exec_ = ScriptedSessionLoopExecutor([_scripted_response("ack")])
    agent = Agent(
        "system",
        model="gpt-5.5",
        memory=store,
        commit_on_forward=True,
    )
    agent._executor_override = exec_
    sess = Session.from_user_message("remember me")
    out = agent.forward(sess)
    commit_ops = [op for op in backend.ops_seen if isinstance(op, MemoryOpCommit)]
    assert len(commit_ops) == 1
    assert commit_ops[0].session_id == str(out.id)


def test_forward_without_commit_does_not_dispatch_commit() -> None:
    backend = _FakeBackend(find_hits=())
    store = backend.open()
    exec_ = ScriptedSessionLoopExecutor([_scripted_response("ack")])
    agent = Agent(
        "system",
        model="gpt-5.5",
        memory=store,
        commit_on_forward=False,
    )
    agent._executor_override = exec_
    sess = Session.from_user_message("nothing important")
    agent.forward(sess)
    assert not any(isinstance(op, MemoryOpCommit) for op in backend.ops_seen)
