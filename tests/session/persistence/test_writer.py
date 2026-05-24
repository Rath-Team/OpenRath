"""Real-fs tests for :class:`rath.session.persistence.SessionWriter`."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from rath.session.chunk import (
    ChunkKind,
    ChunkRow,
    ChunkTable,
    assistant_turn_chunk,
    tool_feedback_chunk,
    user_text_chunk,
)
from rath.session.persistence import SessionWriter, session_file
from rath.session.session import Session


def _new_session(*rows: ChunkRow) -> Session:
    return Session(chunk_table=ChunkTable(rows=tuple(rows)))


def test_header_written_immediately_on_construction(
    _isolate_openrath_home: Path,
) -> None:
    s = _new_session()
    writer = SessionWriter(s)
    # WAL mode: header is written eagerly to the .__partial__ file.
    assert writer.partial_path.is_file()
    assert not writer.path.exists()
    writer.write_chunk(0, user_text_chunk("hi"))
    # Close so the advisory lock is released and the partial file is
    # renamed to the final path.
    writer.close()
    assert writer.path.is_file()
    assert not writer.partial_path.exists()
    text = writer.path.read_text(encoding="utf-8")
    lines = [json.loads(line) for line in text.splitlines() if line.strip()]
    # header + chunk + trailer (close was called above).
    assert lines[0]["record_type"] == "header"
    assert lines[0]["id"] == str(s.id)
    assert lines[1]["record_type"] == "chunk"
    assert lines[1]["index"] == 0
    assert lines[1]["kind"] == "user"
    assert lines[1]["payload"]["content"] == "hi"


def test_each_chunk_flushed_immediately(_isolate_openrath_home: Path) -> None:
    s = _new_session()
    writer = SessionWriter(s)
    writer.write_chunk(0, user_text_chunk("alpha"))
    size_after_one = writer.partial_path.stat().st_size
    writer.write_chunk(1, assistant_turn_chunk(tool_calls=None, content="beta"))
    size_after_two = writer.partial_path.stat().st_size
    assert size_after_two > size_after_one


def test_close_writes_trailer(_isolate_openrath_home: Path) -> None:
    s = _new_session()
    writer = SessionWriter(s)
    writer.write_chunk(0, user_text_chunk("hello"))
    writer.close()
    lines = [
        json.loads(line)
        for line in writer.path.read_text(encoding="utf-8").splitlines()
    ]
    assert lines[-1]["record_type"] == "trailer"
    assert lines[-1]["final_chunk_count"] == 1


def test_close_without_chunks_writes_header_trailer(
    _isolate_openrath_home: Path,
) -> None:
    """WAL header is eager — closing with zero chunks still emits a complete
    JSONL with header + trailer; the partial file is renamed to final."""
    s = _new_session()
    writer = SessionWriter(s)
    writer.close()
    assert writer.path.is_file()
    assert not writer.partial_path.exists()
    lines = [
        json.loads(line)
        for line in writer.path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [line["record_type"] for line in lines] == ["header", "trailer"]
    assert lines[-1]["final_chunk_count"] == 0


def test_abandon_leaves_partial_file(_isolate_openrath_home: Path) -> None:
    """``abandon`` keeps the ``__partial__`` file as a crash signal — it is
    never renamed to the final path and never grows a trailer."""
    s = _new_session()
    writer = SessionWriter(s)
    writer.write_chunk(0, user_text_chunk("partial"))
    writer.abandon()
    assert writer.partial_path.is_file()
    assert not writer.path.exists()
    lines = [
        json.loads(line)
        for line in writer.partial_path.read_text(encoding="utf-8").splitlines()
    ]
    assert all(line.get("record_type") != "trailer" for line in lines)


def test_context_manager_closes_on_success(_isolate_openrath_home: Path) -> None:
    s = _new_session()
    with SessionWriter(s) as writer:
        writer.write_chunk(0, user_text_chunk("done"))
    text = writer.path.read_text(encoding="utf-8")
    assert '"record_type": "trailer"' in text


def test_context_manager_abandons_on_exception(_isolate_openrath_home: Path) -> None:
    s = _new_session()
    writer = SessionWriter(s)
    with pytest.raises(RuntimeError, match="boom"):
        with writer:
            writer.write_chunk(0, user_text_chunk("partial"))
            raise RuntimeError("boom")
    assert writer.partial_path.is_file()
    assert not writer.path.exists()
    text = writer.partial_path.read_text(encoding="utf-8")
    assert '"record_type": "trailer"' not in text


def test_write_after_close_raises(_isolate_openrath_home: Path) -> None:
    s = _new_session()
    writer = SessionWriter(s)
    writer.write_chunk(0, user_text_chunk("hi"))
    writer.close()
    with pytest.raises(RuntimeError, match="closed"):
        writer.write_chunk(1, user_text_chunk("nope"))


def test_path_resolves_to_resolved_sessions_dir(
    _isolate_openrath_home: Path,
) -> None:
    s = _new_session()
    writer = SessionWriter(s)
    assert writer.path == session_file(s.id).resolve()


def test_close_is_idempotent(_isolate_openrath_home: Path) -> None:
    s = _new_session()
    writer = SessionWriter(s)
    writer.write_chunk(0, user_text_chunk("hi"))
    writer.close()
    writer.close()
    # No exception; trailer appears exactly once.
    trailers = [
        json.loads(line)
        for line in writer.path.read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("record_type") == "trailer"
    ]
    assert len(trailers) == 1


def test_explicit_path_override(_isolate_openrath_home: Path, tmp_path: Path) -> None:
    s = _new_session()
    custom = tmp_path / "custom" / f"{uuid4()}.jsonl"
    writer = SessionWriter(s, path=custom)
    writer.write_chunk(0, user_text_chunk("hi"))
    writer.close()
    assert custom.is_file()


def test_tool_result_chunk_round_trips_in_payload(
    _isolate_openrath_home: Path,
) -> None:
    s = _new_session()
    writer = SessionWriter(s)
    writer.write_chunk(0, user_text_chunk("hello"))
    writer.write_chunk(
        1, tool_feedback_chunk("tc-1", "run_shell_command", '{"exit_code": 0}')
    )
    writer.close()
    lines = [
        json.loads(line)
        for line in writer.path.read_text(encoding="utf-8").splitlines()
    ]
    chunk_lines = [line for line in lines if line["record_type"] == "chunk"]
    assert chunk_lines[1]["kind"] == ChunkKind.TOOL_RESULT.value
    assert chunk_lines[1]["payload"]["tool_call_id"] == "tc-1"
    assert chunk_lines[1]["payload"]["name"] == "run_shell_command"
