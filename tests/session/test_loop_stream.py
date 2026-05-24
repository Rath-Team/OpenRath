"""run_session_loop streaming behavior via ``on_event`` (scripted client).

Covers the unified ``on_event`` parameter that replaces the deprecated
``chunk_print`` hook and the standalone ``run_session_loop_stream``.
"""

from __future__ import annotations

import json
from typing import Iterator

import pytest

from rath.backend import get
from rath.flow.agent_param import AgentParam, Provider
from rath.llm import (
    RathLLMChatRequest,
    RathLLMChatResponse,
    RathLLMStreamDelta,
)
from rath.session import (
    Session,
    run_session_loop,
    session_registry,
)
from rath.session.chunk import ChunkKind
from rath.session.loop import StreamingExecutor


@pytest.fixture(autouse=True)
def _clear_active() -> None:
    yield
    session_registry().set_active(None)


class _ScriptedStreamingClient:
    """Streaming-shaped chat client used to script multi-round loops."""

    def __init__(self, scripts: list[list[RathLLMStreamDelta]]) -> None:
        self._scripts = list(scripts)
        self.provider = Provider(model="scripted")

    def complete_stream(self, req: RathLLMChatRequest) -> Iterator[RathLLMStreamDelta]:
        if not self._scripts:
            raise RuntimeError("scripted stream queue empty")
        for d in self._scripts.pop(0):
            yield d

    def complete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
        raise NotImplementedError("scripted client is stream-only")


def test_on_event_refuses_non_streaming_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """``on_event`` requires the resolved client to implement complete_stream(req)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-no-network")
    monkeypatch.delenv("OPENRATH_HOME", raising=False)
    agent = AgentParam(
        Session.from_agent_prompt("sys"),
        Provider(provider_kind="anthropic", model="claude-opus-4-7"),
    )
    backend = get("local")
    with backend.open() as sb:
        user = Session.from_user_message("hi").bind_sandbox(sb)
        out = run_session_loop(
            user,
            agent.agent_session,
            agent_provider=agent.provider,
            on_event=lambda _d: None,
        )
        with pytest.raises(TypeError, match="complete_stream|StreamingChatClient"):
            out.synchronize()


def test_on_event_with_custom_executor_raises() -> None:
    backend = get("local")
    with backend.open() as sb:
        user = Session.from_user_message("hi").bind_sandbox(sb)
        agent = AgentParam(Session.from_agent_prompt("sys"), Provider())
        scripted = StreamingExecutor(_ScriptedStreamingClient([]), lambda _d: None)
        out = run_session_loop(
            user,
            agent.agent_session,
            agent_provider=agent.provider,
            executor=scripted,
            on_event=lambda _d: None,
        )
        with pytest.raises(ValueError, match="custom executor"):
            out.synchronize()


def test_streaming_executor_emits_deltas_and_settles_to_chunk() -> None:
    script = [
        [
            RathLLMStreamDelta(content_delta="Hel"),
            RathLLMStreamDelta(content_delta="lo"),
            RathLLMStreamDelta(finish_reason="stop"),
        ]
    ]
    client = _ScriptedStreamingClient(script)
    events: list[RathLLMStreamDelta] = []
    executor = StreamingExecutor(client, events.append)
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
        out.synchronize()

    assert len(events) == 3
    assistant_rows = [
        r.payload.get("content")
        for r in out.chunk_table.rows
        if r.kind == ChunkKind.ASSISTANT
    ]
    assert "Hello" in assistant_rows


def test_streaming_tool_call_then_stop() -> None:
    args = json.dumps({"path": "."})
    script = [
        [
            RathLLMStreamDelta(
                tool_call_index=0, tool_call_id="tc1", tool_call_name_delta="echo_tool"
            ),
            RathLLMStreamDelta(tool_call_index=0, tool_call_args_delta=args),
            RathLLMStreamDelta(finish_reason="tool_calls"),
        ],
        [
            RathLLMStreamDelta(content_delta="done"),
            RathLLMStreamDelta(finish_reason="stop"),
        ],
    ]
    client = _ScriptedStreamingClient(script)
    events: list[RathLLMStreamDelta] = []
    executor = StreamingExecutor(client, events.append)
    agent = AgentParam(Session.from_agent_prompt("sys"), Provider())
    backend = get("local")

    with backend.open() as sb:
        user = Session.from_user_message("trigger").bind_sandbox(sb)
        out = run_session_loop(
            user,
            agent.agent_session,
            agent_provider=agent.provider,
            executor=executor,
        )

    kinds = [r.kind for r in out.chunk_table.rows]
    assert ChunkKind.TOOL_RESULT in kinds
    assert any(
        r.kind == ChunkKind.ASSISTANT and r.payload.get("content") == "done"
        for r in out.chunk_table.rows
    )
