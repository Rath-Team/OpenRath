"""Regression guard: ``run_session_loop`` rebuilds ``out.chunk_table`` O(turns), not O(rows).

The previous implementation re-materialised ``ChunkTable`` after every appended
row — quadratic in transcript length. The fix syncs ``out.chunk_table`` at most
once per assistant-with-tools turn (plus a single final rebuild after the
loop). This test fakes a two-turn tool-call loop with multiple tools per turn
and asserts the chunk_table identity that tools observe is constant within a
turn.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from rath.backend import get
from rath.flow.agent_param import Provider
from rath.flow.tool.base import FlowToolCall
from rath.llm import (
    RathLLMAssistantMessage,
    RathLLMChatChoice,
    RathLLMChatResponse,
    RathLLMToolCallFunction,
    RathLLMToolCallPart,
)
from rath.session import Session, run_session_loop, session_registry
from tests.session.scripted_loop_executor import ScriptedSessionLoopExecutor


@pytest.fixture(autouse=True)
def _clear_active_session_registry() -> None:
    yield
    session_registry().set_active(None)


class _RecordingTool(FlowToolCall):
    """Tool that records ``id(session.chunk_table)`` on every invocation."""

    def __init__(self) -> None:
        self.observed_ids: list[int] = []

    @property
    def name(self) -> str:
        return "record_id"

    @property
    def description(self) -> str | None:
        return "record session.chunk_table identity"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {"type": "object", "properties": {}, "additionalProperties": False}

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> Any:
        self.observed_ids.append(id(session.chunk_table))
        return "ok"


def _tool_call_response(resp_id: str, call_ids: list[str]) -> RathLLMChatResponse:
    parts = tuple(
        RathLLMToolCallPart(
            id=cid,
            type="function",
            function=RathLLMToolCallFunction(
                name="record_id",
                arguments="{}",
                arguments_parsed={},
                arguments_parse_error=False,
            ),
        )
        for cid in call_ids
    )
    return RathLLMChatResponse(
        id=resp_id,
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


def _stop_response(resp_id: str, text: str) -> RathLLMChatResponse:
    return RathLLMChatResponse(
        id=resp_id,
        choices=(
            RathLLMChatChoice(
                index=0,
                finish_reason="stop",
                message=RathLLMAssistantMessage(content=text),
            ),
        ),
        created=2,
        model="scripted",
    )


def test_chunk_table_identity_is_stable_within_a_turn() -> None:
    """Three tools per turn must observe the same ``chunk_table`` identity."""
    turn1 = _tool_call_response("t1", ["t1-a", "t1-b", "t1-c"])
    turn2 = _tool_call_response("t2", ["t2-a", "t2-b", "t2-c"])
    stop = _stop_response("t3", "done")
    executor = ScriptedSessionLoopExecutor([turn1, turn2, stop])

    tool = _RecordingTool()

    backend = get("local")
    with backend.open() as sandbox:
        user = Session.from_user_message("go").bind_sandbox(sandbox)
        agent = Session.from_agent_prompt("scripted")
        out = run_session_loop(
            user,
            agent,
            agent_provider=Provider(),
            tools=[tool],
            executor=executor,
        )
        # Lazy facade: block on the in-flight materialization before asserting
        # that tools observed a stable ``chunk_table`` identity per turn.
        out.synchronize()

    assert len(tool.observed_ids) == 6, tool.observed_ids
    turn1_ids = set(tool.observed_ids[:3])
    turn2_ids = set(tool.observed_ids[3:])
    # Within a turn: identical chunk_table object reused for every tool call.
    assert len(turn1_ids) == 1, f"per-row rebuild regression in turn 1: {turn1_ids}"
    assert len(turn2_ids) == 1, f"per-row rebuild regression in turn 2: {turn2_ids}"
    # Across turns: a fresh ChunkTable is materialised before the next round.
    assert turn1_ids != turn2_ids
