"""Unit tests for the runtime-internal ``_arun_session_loop``.

These exercise the async session loop directly on the runtime — same
plumbing the public sync ``run_session_loop`` will use in Phase 4, but
without going through the lazy-Session facade so we can stress the loop
body and its resource-keyed parallel tool dispatch in isolation.

LocalBackend is the real backend (no mocks); LLM responses are scripted
via a tiny async executor.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping
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
    """Async counterpart of ``ScriptedSessionLoopExecutor`` for ``_arun_session_loop``."""

    __slots__ = ("_queue",)

    def __init__(self, responses: list[RathLLMChatResponse]) -> None:
        self._queue = list(responses)

    async def acomplete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
        if not self._queue:
            raise RuntimeError("scripted LLM queue empty")
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


def _stop(
    text: str, *, model: str = "scripted", rid: str = "r-stop"
) -> RathLLMChatResponse:
    return RathLLMChatResponse(
        id=rid,
        choices=(
            RathLLMChatChoice(
                index=0,
                finish_reason="stop",
                message=RathLLMAssistantMessage(content=text),
            ),
        ),
        created=1,
        model=model,
    )


def _tool_call(name: str, args: dict[str, Any], *, call_id: str) -> RathLLMToolCallPart:
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


def _tool_round(
    *parts: RathLLMToolCallPart, rid: str = "r-tool"
) -> RathLLMChatResponse:
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


@pytest.fixture(autouse=True)
def _clear_active_session_registry() -> None:
    yield
    session_registry().set_active(None)


def test_arun_session_loop_stop_without_tools() -> None:
    executor = _ScriptedAsyncExecutor([_stop("final answer")])
    agent = AgentParam(
        Session.from_agent_prompt("You are a scripted async assistant."),
        Provider(),
    )

    backend = get("local")
    with backend.open() as sandbox:
        user = Session.from_user_message("Say hi.").bind_sandbox(sandbox)
        out = runtime().run(
            _arun_session_loop(
                user,
                agent.agent_session,
                agent_provider=agent.provider,
                executor=executor,
            )
        )

    assert out.sandbox is sandbox
    assert session_registry().get_active_id() == out.id
    contents = [
        r.payload.get("content")
        for r in out.chunk_table.rows
        if r.kind == ChunkKind.ASSISTANT
    ]
    assert "final answer" in contents


def test_arun_session_loop_write_file_via_tool_then_stop(tmp_path: Any) -> None:
    body = {
        "path": str(tmp_path / "_arun_probe.txt"),
        "content": "ASYNC_LOOP_MARKER",
    }
    first = _tool_round(
        _tool_call("write_workspace_file", body, call_id="tc1"),
        rid="r1",
    )
    second = _stop("wrote it")
    executor = _ScriptedAsyncExecutor([first, second])

    agent = AgentParam(Session.from_agent_prompt("scripted assistant"), Provider())

    backend = get("local")
    with backend.open() as sandbox:
        user = Session.from_user_message("Please write the file.").bind_sandbox(sandbox)
        out = runtime().run(
            _arun_session_loop(
                user,
                agent.agent_session,
                agent_provider=agent.provider,
                executor=executor,
            )
        )

    written = (tmp_path / "_arun_probe.txt").read_text(encoding="utf-8")
    assert written == "ASYNC_LOOP_MARKER"
    kinds = [r.kind for r in out.chunk_table.rows]
    assert ChunkKind.TOOL_RESULT in kinds
    assert ChunkKind.ASSISTANT in kinds


def test_arun_session_loop_parallel_safe_tools_overlap(tmp_path: Any) -> None:
    """Three writes on distinct paths run concurrently."""
    n = 3
    paths = [str(tmp_path / f"par_{i}.txt") for i in range(n)]
    parts = tuple(
        _tool_call(
            "sleepy_write",
            {"path": p, "content": f"slot-{i}"},
            call_id=f"tc{i}",
        )
        for i, p in enumerate(paths)
    )

    # Sleeping tool to make parallelism observable. resource_key returns the
    # path so distinct paths land on distinct queues.
    class _SleepyWrite(FlowToolCall):
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
            time.sleep(0.25)
            with open(arguments["path"], "w", encoding="utf-8") as fp:
                fp.write(str(arguments["content"]))
            return True

    executor = _ScriptedAsyncExecutor([_tool_round(*parts, rid="r-par"), _stop("done")])
    agent = AgentParam(Session.from_agent_prompt("a"), Provider())
    backend = get("local")
    with backend.open() as sandbox:
        user = Session.from_user_message("write three").bind_sandbox(sandbox)
        t0 = time.perf_counter()
        out = runtime().run(
            _arun_session_loop(
                user,
                agent.agent_session,
                agent_provider=agent.provider,
                executor=executor,
                tools=[_SleepyWrite()],
            )
        )
        elapsed = time.perf_counter() - t0

    for p in paths:
        assert open(p, encoding="utf-8").read().startswith("slot-")
    # 3 × 0.25s serial would be 0.75s; parallel must finish well under that.
    assert elapsed < 0.5, f"parallel-safe tools did not overlap; elapsed={elapsed:.3f}s"
    # Transcript order must remain the call order.
    tool_rows = [r for r in out.chunk_table.rows if r.kind == ChunkKind.TOOL_RESULT]
    assert [r.payload.get("tool_call_id") for r in tool_rows] == [
        "tc0",
        "tc1",
        "tc2",
    ]


def test_arun_session_loop_same_key_tools_serialize(tmp_path: Any) -> None:
    """Two writes to the same resource_key path run one after another."""
    path = str(tmp_path / "same.txt")
    parts = tuple(
        _tool_call(
            "counted_write",
            {"path": path, "content": f"v{i}"},
            call_id=f"tc{i}",
        )
        for i in range(2)
    )

    in_flight = 0
    max_in_flight = 0

    import threading

    counter_lock = threading.Lock()

    class _CountedWrite(FlowToolCall):
        parallel_safe = True

        def resource_key(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
            return ("fs:write", str(arguments["path"]))

        @property
        def name(self) -> str:
            return "counted_write"

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
            nonlocal in_flight, max_in_flight
            with counter_lock:
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
            time.sleep(0.15)
            with counter_lock:
                in_flight -= 1
            with open(arguments["path"], "a", encoding="utf-8") as fp:
                fp.write(str(arguments["content"]))
            return True

    executor = _ScriptedAsyncExecutor([_tool_round(*parts, rid="r-same"), _stop("ok")])
    agent = AgentParam(Session.from_agent_prompt("a"), Provider())
    backend = get("local")
    with backend.open() as sandbox:
        user = Session.from_user_message("same path").bind_sandbox(sandbox)
        runtime().run(
            _arun_session_loop(
                user,
                agent.agent_session,
                agent_provider=agent.provider,
                executor=executor,
                tools=[_CountedWrite()],
            )
        )

    assert max_in_flight == 1, (
        f"same resource_key tools must serialize; observed max_in_flight={max_in_flight}"
    )


def test_arun_session_loop_unknown_tool_yields_error_payload() -> None:
    bogus = _tool_call("nope_tool", {"x": 1}, call_id="tc-x")
    executor = _ScriptedAsyncExecutor([_tool_round(bogus, rid="r-bad"), _stop("done")])
    agent = AgentParam(Session.from_agent_prompt("a"), Provider())
    backend = get("local")
    with backend.open() as sandbox:
        user = Session.from_user_message("call unknown").bind_sandbox(sandbox)
        out = runtime().run(
            _arun_session_loop(
                user,
                agent.agent_session,
                agent_provider=agent.provider,
                executor=executor,
            )
        )

    tool_rows = [r for r in out.chunk_table.rows if r.kind == ChunkKind.TOOL_RESULT]
    assert len(tool_rows) == 1
    body = json.loads(tool_rows[0].payload["content"])
    assert body["ok"] is False
    assert body["error_kind"] == "unknown_tool"


def test_arun_session_loop_failing_tool_does_not_break_others(tmp_path: Any) -> None:
    """A failing tool yields a tool_execution_exception body; siblings still run."""

    class _Boom(FlowToolCall):
        parallel_safe = True

        def resource_key(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
            return ("safe", "boom", str(arguments.get("k", "")))

        @property
        def name(self) -> str:
            return "boom"

        @property
        def parameters(self) -> Mapping[str, Any]:
            return {
                "type": "object",
                "properties": {"k": {"type": "string"}},
                "required": ["k"],
            }

        def __call__(self, session: Session, arguments: Mapping[str, Any]) -> Any:
            if arguments.get("k") == "bad":
                raise RuntimeError("explode")
            return {"k": arguments["k"]}

    parts = (
        _tool_call("boom", {"k": "ok-a"}, call_id="tcA"),
        _tool_call("boom", {"k": "bad"}, call_id="tcB"),
        _tool_call("boom", {"k": "ok-b"}, call_id="tcC"),
    )
    executor = _ScriptedAsyncExecutor([_tool_round(*parts, rid="r-mix"), _stop("done")])
    agent = AgentParam(Session.from_agent_prompt("a"), Provider())
    backend = get("local")
    with backend.open() as sandbox:
        user = Session.from_user_message("mixed").bind_sandbox(sandbox)
        out = runtime().run(
            _arun_session_loop(
                user,
                agent.agent_session,
                agent_provider=agent.provider,
                executor=executor,
                tools=[_Boom()],
            )
        )

    tool_rows = [r for r in out.chunk_table.rows if r.kind == ChunkKind.TOOL_RESULT]
    assert [r.payload["tool_call_id"] for r in tool_rows] == ["tcA", "tcB", "tcC"]
    bodies = [json.loads(r.payload["content"]) for r in tool_rows]
    assert bodies[0].get("k") == "ok-a"
    assert bodies[1].get("error_kind") == "tool_execution_exception"
    assert bodies[2].get("k") == "ok-b"
