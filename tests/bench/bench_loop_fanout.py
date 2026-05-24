"""Session-loop fan-out benchmark.

Sweeps the number of parallel-safe ``tool_calls`` in a single assistant
round against a real :class:`~rath.backend.local.LocalBackend` (no LLM
hop — completions are scripted to keep the benchmark focused on
``_arun_session_loop``'s scheduler). Validates the design intent of
phase 3: doubling the fan-out should NOT double the wallclock when each
call hits a distinct ``resource_key``.

This is a benchmark, not a hard assertion — pytest-benchmark records
per-round timings and stats; the harness CI can compare runs to detect
scheduler regressions.
"""

from __future__ import annotations

import json
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
from rath.session import Session

pytestmark = pytest.mark.bench


class _ScriptedAsyncExecutor:
    """Identity-ish scripted exec used inside the session loop."""

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
        import asyncio

        return await asyncio.to_thread(tool, session, dict(arguments or {}))

    def tool_schemas(self) -> tuple[RathLLMFunctionTool, ...]:
        return ()


class _CheapWriteTool(FlowToolCall):
    """Parallel-safe write — each call writes a distinct path."""

    parallel_safe = True

    def resource_key(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
        return ("fs:write", str(arguments["path"]))

    @property
    def name(self) -> str:
        return "cheap_write"

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
        # Real fs write so the bench reflects real dispatch cost.
        with open(arguments["path"], "w", encoding="utf-8") as fp:
            fp.write(str(arguments["content"]))
        return True


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


def _stop_round() -> RathLLMChatResponse:
    return RathLLMChatResponse(
        id="r-stop",
        choices=(
            RathLLMChatChoice(
                index=0,
                finish_reason="stop",
                message=RathLLMAssistantMessage(content="done"),
            ),
        ),
        created=1,
        model="scripted",
    )


@pytest.mark.parametrize("fanout", [1, 2, 4, 8, 16])
def test_bench_loop_fanout(benchmark: Any, fanout: int, tmp_path: Any) -> None:
    """One assistant round with ``fanout`` parallel-safe ``cheap_write`` calls."""

    backend = get("local")
    tool = _CheapWriteTool()

    def _setup() -> tuple[tuple, dict]:
        sb = backend.open()
        agent = AgentParam(Session.from_agent_prompt("s"), Provider())
        user = Session.from_user_message("u").bind_sandbox(sb)
        parts = tuple(
            _tool_call(
                "cheap_write",
                {
                    "path": str(tmp_path / f"fan_{fanout}_{i}.txt"),
                    "content": "x",
                },
                call_id=f"tc{i}",
            )
            for i in range(fanout)
        )
        executor = _ScriptedAsyncExecutor([_tool_round(parts), _stop_round()])
        return (user, agent, executor, sb), {}

    def _bench(user: Any, agent: Any, executor: Any, sb: Any) -> None:
        try:
            runtime().run(
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

    benchmark.pedantic(_bench, setup=_setup, rounds=5, iterations=1, warmup_rounds=1)
