"""``run_session_loop(persist=...)`` end-to-end persistence (real LocalBackend).

These tests replace the old ``persist_chunks()`` hook coverage. Persistence
is now a first-class parameter on ``run_session_loop`` and
``run_session_compress``: ``persist=True`` writes to
``.openrath/sessions/<out.id>.jsonl``, ``persist_path=Path(...)`` writes to
a custom path.
"""

from __future__ import annotations

import json
from pathlib import Path
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
    load_session,
    run_session_loop,
    session_registry,
)
from rath.session.loop import StreamingExecutor
from rath.session.persistence import sessions_dir


@pytest.fixture(autouse=True)
def _clear_active() -> None:
    yield
    session_registry().set_active(None)


class _ScriptedStreamingClient:
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


def test_persist_true_writes_jsonl_under_openrath_home(
    _isolate_openrath_home: Path,
) -> None:
    script = [
        [
            RathLLMStreamDelta(content_delta="ok"),
            RathLLMStreamDelta(finish_reason="stop"),
        ]
    ]
    client = _ScriptedStreamingClient(script)
    executor = StreamingExecutor(client, lambda _d: None)
    agent = AgentParam(Session.from_agent_prompt("sys"), Provider())
    backend = get("local")

    with backend.open() as sb:
        user = Session.from_user_message("hi").bind_sandbox(sb)
        out = run_session_loop(
            user,
            agent.agent_session,
            agent_provider=agent.provider,
            executor=executor,
            persist=True,
        )
        out.synchronize()

    restored = load_session(out.id)
    assert restored.closed is True
    assert restored.chunk_table.rows == out.chunk_table.rows


def test_persist_path_uses_explicit_file(
    _isolate_openrath_home: Path, tmp_path: Path
) -> None:
    script = [
        [
            RathLLMStreamDelta(content_delta="ok"),
            RathLLMStreamDelta(finish_reason="stop"),
        ]
    ]
    client = _ScriptedStreamingClient(script)
    executor = StreamingExecutor(client, lambda _d: None)
    agent = AgentParam(Session.from_agent_prompt("sys"), Provider())
    backend = get("local")
    custom = tmp_path / "subdir" / "transcript.jsonl"

    with backend.open() as sb:
        user = Session.from_user_message("hi").bind_sandbox(sb)
        out = run_session_loop(
            user,
            agent.agent_session,
            agent_provider=agent.provider,
            executor=executor,
            persist_path=custom,
        )
        out.synchronize()

    assert custom.is_file()
    parsed = [
        json.loads(line)
        for line in custom.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    record_types = [p["record_type"] for p in parsed]
    assert record_types[0] == "header"
    assert record_types[-1] == "trailer"
    assert "chunk" in record_types


def test_persist_abandons_file_on_executor_exception(
    _isolate_openrath_home: Path,
) -> None:
    class _BoomExecutor(StreamingExecutor):
        def complete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
            raise RuntimeError("boom")

    client = _ScriptedStreamingClient([])
    executor = _BoomExecutor(client, lambda _d: None)
    agent = AgentParam(Session.from_agent_prompt("sys"), Provider())
    backend = get("local")

    with backend.open() as sb:
        user = Session.from_user_message("hi").bind_sandbox(sb)
        out = run_session_loop(
            user,
            agent.agent_session,
            agent_provider=agent.provider,
            executor=executor,
            persist=True,
        )
        with pytest.raises(RuntimeError, match="boom"):
            out.synchronize()

    # WAL: an abandoned writer keeps the in-flight file under the
    # __partial__ suffix; the final .jsonl is never produced.
    finals = list(sessions_dir().glob("*.jsonl"))
    partials = list(sessions_dir().glob("*.jsonl.__partial__"))
    assert finals == []
    assert len(partials) == 1
    text = partials[0].read_text(encoding="utf-8")
    assert "trailer" not in text
