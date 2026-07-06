"""Session persistence: ``load_session`` round-trip + GC helpers.

Consolidated from (every test function name preserved verbatim):
- test_loader.py    (load_session / list_persisted_sessions / to_resumable_pair)
- test_gc.py        (delete_session / prune_sessions)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
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
    delete_session,
    list_persisted_sessions,
    load_session,
    prune_sessions,
    session_file,
    session_partial_file,
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


def _write_session(content: str = "hi") -> Session:
    s = Session(chunk_table=ChunkTable(rows=()))
    with SessionWriter(s) as w:
        w.write_chunk(0, user_text_chunk(content))
    return s


# ---------------------------------------------------------------------------
# load_session round-trip + error paths
# ---------------------------------------------------------------------------


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
    # explicitly nudge via a no-op sleep.
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


@pytest.mark.parametrize("bad_id", ["../escape", "/tmp/escape", "not-a-uuid"])
def test_session_paths_reject_path_like_ids(
    _isolate_openrath_home: Path,
    bad_id: str,
) -> None:
    with pytest.raises(ValueError, match="session_id must be a UUID"):
        session_file(bad_id)
    with pytest.raises(ValueError, match="session_id must be a UUID"):
        session_partial_file(bad_id)


# ---------------------------------------------------------------------------
# GC: delete + prune
# ---------------------------------------------------------------------------


def test_delete_session_removes_file(_isolate_openrath_home: Path) -> None:
    s = _write_session()
    assert session_file(s.id).is_file()
    assert delete_session(s.id) is True
    assert not session_file(s.id).is_file()


def test_delete_session_returns_false_when_absent(
    _isolate_openrath_home: Path,
) -> None:
    assert delete_session(uuid.uuid4()) is False


def test_delete_session_is_idempotent(_isolate_openrath_home: Path) -> None:
    s = _write_session()
    assert delete_session(s.id) is True
    assert delete_session(s.id) is False


def test_prune_sessions_removes_only_older_than_cutoff(
    _isolate_openrath_home: Path,
) -> None:
    old = _write_session("old one")
    new = _write_session("new one")

    # Rewrite the old session's header timestamp to long ago by editing the
    # file directly — this is the cleanest way to simulate "older than".
    old_path = session_file(old.id)
    lines = old_path.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    ancient = datetime.now(timezone.utc) - timedelta(days=400)
    header["created_at"] = ancient.isoformat()
    lines[0] = json.dumps(header, ensure_ascii=False)
    old_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    removed = prune_sessions(older_than=timedelta(days=30))
    assert removed == [old.id]
    surviving = {m.id for m in list_persisted_sessions()}
    assert surviving == {new.id}


def test_prune_sessions_empty_when_nothing_old(_isolate_openrath_home: Path) -> None:
    _write_session("fresh")
    assert prune_sessions(older_than=timedelta(days=30)) == []


def test_prune_sessions_skips_unparseable_files(
    _isolate_openrath_home: Path,
) -> None:
    """Files that don't parse aren't pruned (manual cleanup is safer)."""
    from rath.session.persistence.paths import ensure_sessions_dir

    target_dir = ensure_sessions_dir()
    junk = target_dir / "not-a-uuid.jsonl"
    junk.write_text("garbage\n", encoding="utf-8")
    # Should not raise; just returns empty.
    removed = prune_sessions(older_than=timedelta(seconds=0))
    assert removed == []
    assert junk.is_file()


@pytest.mark.parametrize("days", [1, 7, 365])
def test_prune_sessions_respects_arbitrary_cutoffs(
    _isolate_openrath_home: Path, days: int
) -> None:
    s = _write_session("s")
    path = session_file(s.id)
    lines = path.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    header["created_at"] = (
        datetime.now(timezone.utc) - timedelta(days=days + 1)
    ).isoformat()
    lines[0] = json.dumps(header, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    removed = prune_sessions(older_than=timedelta(days=days))
    assert removed == [s.id]
