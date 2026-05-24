"""Phase 4 lazy session contract — :class:`Session._pending` + :meth:`synchronize`.

These tests pin down the user-visible behavior of PyTorch-style lazy
:class:`~rath.session.session.Session` returned from
:func:`~rath.session.loop.run_session_loop`:

- ``out`` is returned immediately; ``_pending.done()`` is False until the
  runtime publishes the materialization.
- Lineage attributes (``id``, ``parent_session_ids``, ``lineage_operator``,
  etc.) are eager — reading them does NOT trigger ``synchronize()``.
- Reading ``chunk_table`` or ``cumulative_usage`` blocks until materialized
  (concurrency invariant 3: data fields written before ``_pending`` is
  cleared).
- Multi-thread ``synchronize()`` racing on one Session only materializes
  once (concurrency invariant 4).
- Exceptions raised inside the loop propagate through ``synchronize()``.
- ``Workflow.__call__`` auto-joins a lazy input (concurrency invariant 7).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from typing import Any

import pytest

from rath.backend import get
from rath.flow.agent_param import AgentParam, Provider
from rath.flow.workflow import Workflow
from rath.llm import (
    RathLLMAssistantMessage,
    RathLLMChatChoice,
    RathLLMChatRequest,
    RathLLMChatResponse,
    RathLLMTokenUsage,
)
from rath.session import Session, run_session_loop, session_registry
from tests.session.scripted_loop_executor import ScriptedSessionLoopExecutor


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    yield
    session_registry().set_active(None)


def _stop_response(content: str = "ok") -> RathLLMChatResponse:
    return RathLLMChatResponse(
        id="lazy-test",
        choices=(
            RathLLMChatChoice(
                index=0,
                finish_reason="stop",
                message=RathLLMAssistantMessage(content=content),
            ),
        ),
        created=1,
        model="scripted",
        usage=RathLLMTokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
    )


class _SlowExecutor:
    """Scripted executor that sleeps inside ``complete`` so we can observe the
    pre-materialization window from the calling thread.
    """

    __slots__ = ("_resp", "_delay", "_called")

    def __init__(self, resp: RathLLMChatResponse, delay: float) -> None:
        self._resp = resp
        self._delay = delay
        self._called = threading.Event()

    def complete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
        self._called.set()
        time.sleep(self._delay)
        return self._resp

    def dispatch_tool(
        self, session: Session, tool: Any, arguments: Mapping[str, Any]
    ) -> Any:
        raise AssertionError("no tools in this test")

    def tool_schemas(self):  # type: ignore[no-untyped-def]
        return ()


def test_lazy_returns_immediately_and_lineage_is_eager() -> None:
    """``run_session_loop`` returns before the loop finishes; lineage is set."""
    slow = _SlowExecutor(_stop_response(), delay=0.5)
    agent = AgentParam(Session.from_agent_prompt("sys"), Provider())
    backend = get("local")

    with backend.open() as sb:
        user = Session.from_user_message("hi").bind_sandbox(sb)
        t0 = time.perf_counter()
        out = run_session_loop(
            user,
            agent.agent_session,
            agent_provider=agent.provider,
            executor=slow,
        )
        submit_elapsed = time.perf_counter() - t0

        # The submission should return well before the 0.5s delay.
        assert submit_elapsed < 0.25, (
            f"run_session_loop blocked for {submit_elapsed:.3f}s; expected lazy return"
        )
        assert out._pending is not None
        # Lineage is eager.
        assert out.parent_session_ids == (user.id, agent.agent_session.id)
        assert out.lineage_operator == "run_session_loop"
        assert out.lineage_kind.value.endswith("session_loop")
        # Sandbox is bound eagerly.
        assert out.sandbox is sb

        # Now block on materialization.
        out.synchronize()
        assert out._pending is None
        assert any(r.kind.value == "assistant" for r in out._chunk_table.rows)


def test_chunk_table_property_blocks_until_materialized() -> None:
    """Reading ``out.chunk_table`` implicitly blocks on ``_pending``."""
    slow = _SlowExecutor(_stop_response("payload"), delay=0.2)
    agent = AgentParam(Session.from_agent_prompt("sys"), Provider())
    backend = get("local")
    with backend.open() as sb:
        user = Session.from_user_message("hi").bind_sandbox(sb)
        out = run_session_loop(
            user,
            agent.agent_session,
            agent_provider=agent.provider,
            executor=slow,
        )
        # First read forces synchronize.
        rows = out.chunk_table.rows
        assert out._pending is None
        assert any(
            r.payload.get("content") == "payload"
            for r in rows
            if r.kind.value == "assistant"
        )


def test_cumulative_usage_property_blocks_until_materialized() -> None:
    slow = _SlowExecutor(_stop_response(), delay=0.15)
    agent = AgentParam(Session.from_agent_prompt("sys"), Provider())
    backend = get("local")
    with backend.open() as sb:
        user = Session.from_user_message("hi").bind_sandbox(sb)
        out = run_session_loop(
            user,
            agent.agent_session,
            agent_provider=agent.provider,
            executor=slow,
        )
        usage = out.cumulative_usage
        assert usage is not None
        assert usage.total_tokens == 3
        assert out._pending is None


def test_synchronize_is_idempotent_under_thread_race() -> None:
    """Concurrency invariant 4: multi-thread sync materializes once.

    All callers see the same materialized state; the data fields are written
    once and ``_pending`` flips to ``None`` exactly once.
    """
    executor = ScriptedSessionLoopExecutor([_stop_response("once")])
    agent = AgentParam(Session.from_agent_prompt("sys"), Provider())
    backend = get("local")
    with backend.open() as sb:
        user = Session.from_user_message("hi").bind_sandbox(sb)
        out = run_session_loop(
            user,
            agent.agent_session,
            agent_provider=agent.provider,
            executor=executor,
        )
        results: list[Session] = []
        barrier = threading.Barrier(8)

        def _sync() -> None:
            barrier.wait()
            results.append(out.synchronize())

        threads = [threading.Thread(target=_sync) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r is out for r in results)
        assert out._pending is None
        # _chunk_table is stable across all observers
        rows = out._chunk_table.rows
        assert any(
            r.payload.get("content") == "once"
            for r in rows
            if r.kind.value == "assistant"
        )


def test_exception_inside_loop_propagates_through_synchronize() -> None:
    class _BoomExecutor:
        def complete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
            raise RuntimeError("kaboom")

        def dispatch_tool(self, *_a, **_k):  # type: ignore[no-untyped-def]
            raise AssertionError("not used")

        def tool_schemas(self):  # type: ignore[no-untyped-def]
            return ()

    agent = AgentParam(Session.from_agent_prompt("sys"), Provider())
    backend = get("local")
    with backend.open() as sb:
        user = Session.from_user_message("hi").bind_sandbox(sb)
        out = run_session_loop(
            user,
            agent.agent_session,
            agent_provider=agent.provider,
            executor=_BoomExecutor(),
        )
        with pytest.raises(RuntimeError, match="kaboom"):
            out.synchronize()
        # _pending was cleared even on error so a second access does not
        # block forever — it will read the empty materialized state.
        assert out._pending is None


def test_workflow_call_auto_joins_lazy_input() -> None:
    """Concurrency invariant 7: ``Workflow.__call__`` synchronizes a lazy input
    before invoking ``forward``.
    """
    captured: list[Session] = []

    class _AssertJoined(Workflow):
        def forward(self, session: Session) -> Session:
            # If auto-join works, ``session._pending`` is None here.
            captured.append(session)
            assert session._pending is None
            return session

    slow = _SlowExecutor(_stop_response(), delay=0.15)
    agent = AgentParam(Session.from_agent_prompt("sys"), Provider())
    backend = get("local")
    with backend.open() as sb:
        user = Session.from_user_message("hi").bind_sandbox(sb)
        out = run_session_loop(
            user,
            agent.agent_session,
            agent_provider=agent.provider,
            executor=slow,
        )
        assert out._pending is not None
        result = _AssertJoined()(out)
        assert result is out
        assert captured == [out]
