"""Verify ``FlowToolCall.resource_key`` actually drives parallel vs serial dispatch.

These tests exercise :func:`_arun_session_loop` end-to-end with a real
``LocalBackend`` and a scripted async executor that emits multiple
``tool_calls`` in a single round. The tools sleep so timing is observable.

Invariants asserted:

- Same ``resource_key`` → serial: at most one tool with that key is ever
  in flight (counter peak == 1, even when N concurrent calls are issued).
- Distinct ``resource_key`` → parallel: N concurrent calls finish in
  much less than N × per-call latency.
- Transcript ordering: the ``tool`` rows always appear in the original
  ``tool_calls`` order, regardless of which tool finished first.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Mapping
from typing import Any

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
from rath.session import Session
from rath.session.chunk import ChunkKind


class _ScriptedAsyncExecutor:
    __slots__ = ("_queue",)

    def __init__(self, responses: list[RathLLMChatResponse]) -> None:
        self._queue = list(responses)

    async def acomplete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
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


def _tc(name: str, args: dict[str, Any], call_id: str) -> RathLLMToolCallPart:
    arg_str = json.dumps(args)
    return RathLLMToolCallPart(
        id=call_id,
        type="function",
        function=RathLLMToolCallFunction(
            name=name,
            arguments=arg_str,
            arguments_parsed=args,
            arguments_parse_error=False,
        ),
    )


def _tool_round(*parts: RathLLMToolCallPart, rid: str) -> RathLLMChatResponse:
    return RathLLMChatResponse(
        id=rid,
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


def _stop() -> RathLLMChatResponse:
    return RathLLMChatResponse(
        id="r-stop",
        choices=(
            RathLLMChatChoice(
                index=0,
                finish_reason="stop",
                message=RathLLMAssistantMessage(content="done"),
            ),
        ),
        created=2,
        model="scripted",
    )


class _CountingTool(FlowToolCall):
    """Records peak concurrency seen inside ``__call__``; keys on ``arguments['key']``."""

    parallel_safe = True

    def __init__(self, *, sleep_s: float = 0.2) -> None:
        self.sleep_s = sleep_s
        self._lock = threading.Lock()
        self.in_flight = 0
        self.peak = 0
        self.completions: list[str] = []

    def resource_key(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
        return ("res", str(arguments["key"]))

    @property
    def name(self) -> str:
        return "counted"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "label": {"type": "string"},
            },
            "required": ["key", "label"],
        }

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> Any:
        with self._lock:
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
        time.sleep(self.sleep_s)
        with self._lock:
            self.in_flight -= 1
            self.completions.append(str(arguments["label"]))
        return {"label": arguments["label"]}


def test_same_resource_key_calls_serialize() -> None:
    tool = _CountingTool(sleep_s=0.15)
    parts = tuple(
        _tc("counted", {"key": "shared", "label": f"L{i}"}, call_id=f"tc{i}")
        for i in range(4)
    )
    executor = _ScriptedAsyncExecutor([_tool_round(*parts, rid="r"), _stop()])
    backend = get("local")
    agent = AgentParam(Session.from_agent_prompt("a"), Provider())
    with backend.open() as sandbox:
        user = Session.from_user_message("u").bind_sandbox(sandbox)
        out = runtime().run(
            _arun_session_loop(
                user,
                agent.agent_session,
                agent_provider=agent.provider,
                executor=executor,
                tools=[tool],
            )
        )
    assert tool.peak == 1, (
        f"shared resource_key must serialize; peak in-flight={tool.peak}"
    )
    # Transcript order must be the call order, not completion order.
    tool_rows = [r for r in out.chunk_table.rows if r.kind == ChunkKind.TOOL_RESULT]
    assert [r.payload["tool_call_id"] for r in tool_rows] == [
        "tc0",
        "tc1",
        "tc2",
        "tc3",
    ]


def test_distinct_resource_keys_run_in_parallel() -> None:
    tool = _CountingTool(sleep_s=0.2)
    parts = tuple(
        _tc("counted", {"key": f"k{i}", "label": f"L{i}"}, call_id=f"tc{i}")
        for i in range(4)
    )
    executor = _ScriptedAsyncExecutor([_tool_round(*parts, rid="r"), _stop()])
    backend = get("local")
    agent = AgentParam(Session.from_agent_prompt("a"), Provider())
    with backend.open() as sandbox:
        user = Session.from_user_message("u").bind_sandbox(sandbox)
        t0 = time.perf_counter()
        out = runtime().run(
            _arun_session_loop(
                user,
                agent.agent_session,
                agent_provider=agent.provider,
                executor=executor,
                tools=[tool],
            )
        )
        elapsed = time.perf_counter() - t0
    assert tool.peak >= 2, (
        f"distinct resource_key should overlap; peak in-flight={tool.peak}"
    )
    # 4 × 0.2s serial = 0.8s; comfortable bound for parallel overlap.
    assert elapsed < 0.6, (
        f"distinct keys did not run in parallel; elapsed={elapsed:.3f}s"
    )
    tool_rows = [r for r in out.chunk_table.rows if r.kind == ChunkKind.TOOL_RESULT]
    assert [r.payload["tool_call_id"] for r in tool_rows] == [
        "tc0",
        "tc1",
        "tc2",
        "tc3",
    ]


def test_default_resource_key_serializes_non_parallel_safe_tools() -> None:
    """Tools that do not opt in to ``parallel_safe`` collapse onto one queue."""

    class _UnsafeCounted(_CountingTool):
        parallel_safe = False

        def resource_key(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:  # type: ignore[override]
            # Use the default ABC behavior: non-parallel-safe → ("global",)
            return FlowToolCall.resource_key(self, arguments)

    tool = _UnsafeCounted(sleep_s=0.12)
    parts = tuple(
        _tc("counted", {"key": f"k{i}", "label": f"L{i}"}, call_id=f"tc{i}")
        for i in range(3)
    )
    executor = _ScriptedAsyncExecutor([_tool_round(*parts, rid="r"), _stop()])
    backend = get("local")
    agent = AgentParam(Session.from_agent_prompt("a"), Provider())
    with backend.open() as sandbox:
        user = Session.from_user_message("u").bind_sandbox(sandbox)
        runtime().run(
            _arun_session_loop(
                user,
                agent.agent_session,
                agent_provider=agent.provider,
                executor=executor,
                tools=[tool],
            )
        )
    assert tool.peak == 1, (
        f"non-parallel-safe tools must serialize on ('global',); peak={tool.peak}"
    )
