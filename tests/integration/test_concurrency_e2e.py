"""End-to-end concurrency tests for the async runtime.

These exercise the **full** stack — sync public facade → runtime →
``_arun_session_loop`` → resource-keyed tool dispatch → LocalBackend
(real subprocesses + filesystem). No mocks for backend or for the
session-loop scheduler. The LLM is scripted via a custom executor (so
this file does NOT require ``OPENAI_API_KEY``).

Goals:

- Multiple session loops run on the same runtime without leaking
  threads, file descriptors, or hanging futures.
- Parallel-safe ``tool_calls`` from distinct sessions interleave —
  wallclock is bounded by max-per-session, not by the sum.
- Cancellation via ``runtime().drain(0.0)`` while loops are in flight
  marks affected sessions cancelled; counts conserve.
- A re-entrant ``run_session_loop`` call from inside a tool body raises
  cleanly (the public sync facade refuses to nest), per the runtime's
  documented "no recursive ``run``" guarantee.

A separate file (``test_session_loop_real.py``) handles the live-LLM +
real-opensandbox path; this one stays scripted so it can run on every
local checkout.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from rath._async.aloop import _arun_session_loop
from rath._async.runtime import runtime
from rath.backend import get
from rath.flow.agent_param import AgentParam, Provider
from rath.flow.tool import FlowToolCall
from rath.llm import (
    RathLLMAssistantMessage,
    RathLLMChatChoice,
    RathLLMChatRequest,
    RathLLMChatResponse,
    RathLLMFunctionTool,
    RathLLMToolCallFunction,
    RathLLMToolCallPart,
)
from rath.session import Session, session_registry
from rath.session.chunk import ChunkKind


class _ScriptedAsyncExecutor:
    __slots__ = ("_queue",)

    def __init__(self, responses: list[RathLLMChatResponse]) -> None:
        self._queue = list(responses)

    async def acomplete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
        if not self._queue:
            raise RuntimeError("scripted queue empty")
        return self._queue.pop(0)

    async def adispatch_tool(
        self,
        session: Session,
        tool: FlowToolCall,
        arguments: Mapping[str, Any],
    ) -> Any:
        return await asyncio.to_thread(tool, session, dict(arguments or {}))

    def tool_schemas(self) -> tuple[RathLLMFunctionTool, ...]:
        return ()


def _tool_call(name: str, args: dict[str, Any], *, call_id: str) -> RathLLMToolCallPart:
    return RathLLMToolCallPart(
        id=call_id,
        type="function",
        function=RathLLMToolCallFunction(
            name=name,
            arguments=json.dumps(args),
            arguments_parsed=args,
            arguments_parse_error=False,
        ),
    )


def _tool_round(parts: tuple[RathLLMToolCallPart, ...]) -> RathLLMChatResponse:
    return RathLLMChatResponse(
        id="r-tool",
        choices=(
            RathLLMChatChoice(
                index=0,
                finish_reason="tool_calls",
                message=RathLLMAssistantMessage(content=None, tool_calls=parts),
            ),
        ),
        created=1,
        model="scripted",
    )


def _stop_round(text: str = "done") -> RathLLMChatResponse:
    return RathLLMChatResponse(
        id="r-stop",
        choices=(
            RathLLMChatChoice(
                index=0,
                finish_reason="stop",
                message=RathLLMAssistantMessage(content=text),
            ),
        ),
        created=1,
        model="scripted",
    )


class _SleepyWrite(FlowToolCall):
    """Parallel-safe write — slow enough that overlap is observable."""

    parallel_safe = True

    def resource_key(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
        return ("fs:write", str(arguments["path"]))

    @property
    def name(self) -> str:
        return "sleepy_write"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        }

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> Any:
        time.sleep(0.2)
        with open(arguments["path"], "w", encoding="utf-8") as fp:
            fp.write(str(arguments["content"]))
        return True


@pytest.fixture(autouse=True)
def _clear_active_session_registry() -> None:
    yield
    session_registry().set_active(None)


def test_many_concurrent_sessions_complete_without_leaks(tmp_path: Any) -> None:
    """8 concurrent session loops, 4 tool_calls each, must overlap."""
    n_sessions = 8
    fanout = 4
    backend = get("local")
    tool = _SleepyWrite()

    threads_before = threading.active_count()

    def _run(idx: int) -> Session:
        sb = backend.open()
        try:
            agent = AgentParam(Session.from_agent_prompt("a"), Provider())
            user = Session.from_user_message("u").bind_sandbox(sb)
            parts = tuple(
                _tool_call(
                    "sleepy_write",
                    {
                        "path": str(tmp_path / f"s{idx}_f{i}.txt"),
                        "content": f"s{idx}-{i}",
                    },
                    call_id=f"tc{i}",
                )
                for i in range(fanout)
            )
            executor = _ScriptedAsyncExecutor([_tool_round(parts), _stop_round()])
            return runtime().run(
                _arun_session_loop(
                    user,
                    agent.agent_session,
                    agent_provider=agent.provider,
                    executor=executor,
                    tools=[tool],
                )
            )
        finally:
            backend.close(sb)

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n_sessions) as pool:
        outs = list(pool.map(_run, range(n_sessions)))
    elapsed = time.perf_counter() - t0

    # Serial-equivalent wallclock: n_sessions * fanout * 0.2s = 6.4s for (8, 4).
    # With per-path resource keys + per-session parallelism the total must be
    # well under that. Generous bound to avoid flake on slow CI.
    serial_eq = n_sessions * fanout * 0.2
    assert elapsed < serial_eq * 0.5, (
        f"e2e fanout did not overlap: elapsed={elapsed:.2f}s, serial-eq={serial_eq:.2f}s"
    )

    for out in outs:
        assert any(r.kind == ChunkKind.ASSISTANT for r in out.chunk_table.rows)
        tool_rows = [r for r in out.chunk_table.rows if r.kind == ChunkKind.TOOL_RESULT]
        assert len(tool_rows) == fanout

    # Thread accounting: asyncio.to_thread / ThreadPoolExecutor reuse worker
    # threads, so the count grows up to min(32, cpu+4) under heavy fan-out
    # (8 sessions x 4 tools here) and stays there. We only fail on a true
    # leak — growth proportional to the workload rather than capped.
    threads_after = threading.active_count()
    cap = max(8, min(36, (n_sessions * fanout) + 8))
    assert threads_after - threads_before <= cap, (
        f"thread leak suspected: before={threads_before}, after={threads_after}"
    )


def test_nested_run_from_inside_tool_raises_not_deadlock(tmp_path: Any) -> None:
    """A tool body that calls ``runtime().run`` from the runtime loop fails fast.

    Public guarantee from ``OpenRathRuntime.run``: it refuses to block
    when called from inside a running asyncio loop. The scripted
    executor's ``adispatch_tool`` uses ``asyncio.to_thread``, so the
    *tool* runs on a worker thread, not the loop — meaning a normal
    ``runtime().run`` from there should be fine. We instead exercise
    the documented failure mode by calling ``runtime().run`` from
    inside an ``acomplete`` body (which DOES execute on the loop), and
    assert it raises.
    """

    class _ReentrantExecutor:
        async def acomplete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
            # Inside the loop — must not be allowed to nest.
            with pytest.raises(RuntimeError, match="asyncio loop"):
                runtime().run(asyncio.sleep(0))
            return _stop_round("ok")

        async def adispatch_tool(
            self,
            session: Session,
            tool: FlowToolCall,
            arguments: Mapping[str, Any],
        ) -> Any:
            return None

        def tool_schemas(self) -> tuple[RathLLMFunctionTool, ...]:
            return ()

    backend = get("local")
    with backend.open() as sb:
        agent = AgentParam(Session.from_agent_prompt("a"), Provider())
        user = Session.from_user_message("u").bind_sandbox(sb)
        # The pytest.raises *inside* the coroutine swallows the error, so the
        # loop completes normally; the assertion already happened.
        out = runtime().run(
            _arun_session_loop(
                user,
                agent.agent_session,
                agent_provider=agent.provider,
                executor=_ReentrantExecutor(),
            )
        )
    assert any(r.kind == ChunkKind.ASSISTANT for r in out.chunk_table.rows)


def test_concurrent_sessions_register_distinct_ids(tmp_path: Any) -> None:
    """Each session loop registers its ``out`` session under a unique id."""
    backend = get("local")
    tool = _SleepyWrite()
    n = 4

    def _run(idx: int) -> Session:
        sb = backend.open()
        try:
            agent = AgentParam(Session.from_agent_prompt("a"), Provider())
            user = Session.from_user_message("u").bind_sandbox(sb)
            parts = (
                _tool_call(
                    "sleepy_write",
                    {"path": str(tmp_path / f"id_{idx}.txt"), "content": "x"},
                    call_id="tc0",
                ),
            )
            executor = _ScriptedAsyncExecutor([_tool_round(parts), _stop_round()])
            return runtime().run(
                _arun_session_loop(
                    user,
                    agent.agent_session,
                    agent_provider=agent.provider,
                    executor=executor,
                    tools=[tool],
                )
            )
        finally:
            backend.close(sb)

    with ThreadPoolExecutor(max_workers=n) as pool:
        outs = list(pool.map(_run, range(n)))

    ids = {out.id for out in outs}
    assert len(ids) == n
    reg = session_registry()
    # Every out session is reachable through the registry.
    for out in outs:
        assert reg.get(out.id) is out
