"""Round-trip + error-path tests for :func:`load_session` / :func:`list_persisted_sessions`."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from rath.backend.abc import BackendSandboxSpec
from rath.session.chunk import (
    ChunkKind,
    ChunkTable,
    assistant_turn_chunk,
    system_text_chunk,
    tool_feedback_chunk,
    user_text_chunk,
)
from rath.session.graph.kind import LineageKind
from rath.session.persistence import (
    PersistenceError,
    SessionWriter,
    list_persisted_sessions,
    load_session,
    session_file,
)
from rath.session.session import Session


def _build_full_session() -> Session:
    """A session with all 4 chunk kinds and a non-trivial sandbox spec."""
    s = Session(
        chunk_table=ChunkTable(rows=()),
        sandbox_backend="local",
        _sandbox_open_spec=BackendSandboxSpec(working_dir="/tmp/x"),
        lineage_operator="run_session_loop",
        lineage_kind=LineageKind.OP_SESSION_LOOP,
        lineage_extras=(("loop.truncated", True), ("note", "demo")),
    )
    return s


def test_round_trip_full_session(_isolate_openrath_home: Path) -> None:
    s = _build_full_session()
    rows = [
        system_text_chunk("You are helpful."),
        user_text_chunk("Hi"),
        assistant_turn_chunk(tool_calls=None, content="Hello!"),
        tool_feedback_chunk("tc-1", "noop", '{"ok": true}'),
    ]
    with SessionWriter(s, sandbox_handle_id="abc-123") as writer:
        for idx, row in enumerate(rows):
            writer.write_chunk(idx, row)

    loaded = load_session(s.id)
    assert loaded.closed is True
    assert loaded.header.id == s.id
    assert loaded.header.sandbox_backend == "local"
    assert loaded.header.sandbox_spec is not None
    assert loaded.header.sandbox_spec.working_dir == "/tmp/x"
    assert loaded.header.sandbox_handle_id == "abc-123"
    assert loaded.header.lineage_operator == "run_session_loop"
    assert loaded.header.lineage_kind == LineageKind.OP_SESSION_LOOP
    assert ("loop.truncated", True) in loaded.header.lineage_extras
    # Chunk round-trip preserves kind + payload exactly.
    assert tuple(r.kind for r in loaded.chunk_table.rows) == (
        ChunkKind.SYSTEM,
        ChunkKind.USER,
        ChunkKind.ASSISTANT,
        ChunkKind.TOOL_RESULT,
    )
    assert loaded.chunk_table.rows[0].payload["content"] == "You are helpful."
    assert loaded.chunk_table.rows[2].payload["tool_calls"] is None
    assert loaded.chunk_table.rows[3].payload["tool_call_id"] == "tc-1"


def test_missing_trailer_marks_session_open(_isolate_openrath_home: Path) -> None:
    s = Session(chunk_table=ChunkTable(rows=()))
    writer = SessionWriter(s)
    writer.write_chunk(0, user_text_chunk("hello"))
    writer.abandon()  # simulates kill -9
    loaded = load_session(s.id)
    assert loaded.closed is False
    assert len(loaded.chunk_table.rows) == 1


def test_partial_final_line_dropped_silently(_isolate_openrath_home: Path) -> None:
    """A trailing unterminated line is treated as a crashed write and ignored."""
    s = Session(chunk_table=ChunkTable(rows=()))
    writer = SessionWriter(s)
    writer.write_chunk(0, user_text_chunk("hello"))
    writer.abandon()
    # Append an unterminated, malformed line at the end.
    with writer.partial_path.open("a", encoding="utf-8") as fp:
        fp.write('{"record_type": "chunk", "index": 1, "kind": "u')
    loaded = load_session(s.id)
    assert loaded.closed is False
    assert len(loaded.chunk_table.rows) == 1  # the malformed line is dropped


def test_corrupt_full_line_raises_persistence_error(
    _isolate_openrath_home: Path,
) -> None:
    s = Session(chunk_table=ChunkTable(rows=()))
    writer = SessionWriter(s)
    writer.write_chunk(0, user_text_chunk("hi"))
    writer.abandon()
    with writer.partial_path.open("a", encoding="utf-8") as fp:
        fp.write("{this is not JSON}\n")
    with pytest.raises(PersistenceError, match="invalid JSON"):
        load_session(s.id)


def test_missing_file_raises_persistence_error(
    _isolate_openrath_home: Path,
) -> None:
    with pytest.raises(PersistenceError, match="not found"):
        load_session(uuid4())


def test_list_persisted_sessions_orders_by_created_at(
    _isolate_openrath_home: Path,
) -> None:
    s1 = Session(chunk_table=ChunkTable(rows=()))
    with SessionWriter(s1) as w:
        w.write_chunk(0, user_text_chunk("one"))
    # The next session's header carries a later created_at since datetime.now
    # increases between calls; if the test environment is too fast we
    # explicitly nudge via a no-op sleep. The clock resolution we observed in
    # CI is fine without one, but make the intent explicit:
    import time

    time.sleep(0.005)
    s2 = Session(chunk_table=ChunkTable(rows=()))
    with SessionWriter(s2) as w:
        w.write_chunk(0, user_text_chunk("two"))

    metas = list_persisted_sessions()
    assert [m.id for m in metas] == [s1.id, s2.id]
    assert all(m.closed for m in metas)
    assert all(m.chunk_count == 1 for m in metas)


def test_list_empty_when_dir_missing(_isolate_openrath_home: Path) -> None:
    # No SessionWriter has been opened yet, so sessions/ does not exist.
    assert list_persisted_sessions() == []


def test_explicit_path_load(_isolate_openrath_home: Path, tmp_path: Path) -> None:
    s = Session(chunk_table=ChunkTable(rows=()))
    custom = tmp_path / "custom.jsonl"
    with SessionWriter(s, path=custom) as w:
        w.write_chunk(0, user_text_chunk("custom"))
    loaded = load_session(s.id, path=custom)
    assert loaded.path == custom.resolve()
    assert loaded.chunk_table.rows[0].payload["content"] == "custom"


def test_to_resumable_pair_preserves_chunk_table(
    _isolate_openrath_home: Path,
) -> None:
    s = _build_full_session()
    with SessionWriter(s) as w:
        w.write_chunk(0, system_text_chunk("Be brief."))
        w.write_chunk(1, user_text_chunk("hi"))
    loaded = load_session(s.id)
    user, agent = loaded.to_resumable_pair()
    assert user.chunk_table == loaded.chunk_table
    assert user.sandbox_backend == "local"
    assert user._sandbox_open_spec is not None
    assert user._sandbox_open_spec.working_dir == "/tmp/x"
    # Agent session pulls the system prompt from the persisted history.
    assert agent.chunk_table.rows[0].kind == ChunkKind.SYSTEM
    assert agent.chunk_table.rows[0].payload["content"] == "Be brief."


def test_to_resumable_pair_override_agent_prompt(
    _isolate_openrath_home: Path,
) -> None:
    s = Session(chunk_table=ChunkTable(rows=()))
    with SessionWriter(s) as w:
        w.write_chunk(0, user_text_chunk("hi"))
    loaded = load_session(s.id)
    _, agent = loaded.to_resumable_pair(agent_prompt="new prompt")
    assert agent.chunk_table.rows[0].kind == ChunkKind.SYSTEM
    assert agent.chunk_table.rows[0].payload["content"] == "new prompt"


def test_session_file_path_under_resolved_dir(_isolate_openrath_home: Path) -> None:
    sid = uuid4()
    expected = session_file(sid)
    assert str(expected).endswith(f"{sid}.jsonl")
