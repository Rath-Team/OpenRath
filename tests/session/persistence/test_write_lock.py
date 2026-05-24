"""Cross-process advisory write lock for SessionWriter.

Real fs, no mocks — opens two writers against the same session id and
verifies the second one fails fast.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rath.session.chunk import ChunkTable, user_text_chunk
from rath.session.persistence import PersistenceError, SessionWriter
from rath.session.session import Session


def test_second_writer_against_same_id_fails(
    _isolate_openrath_home: Path,
) -> None:
    s = Session(chunk_table=ChunkTable(rows=()))
    w1 = SessionWriter(s)
    w1.write_chunk(0, user_text_chunk("first"))
    # Same session id → same partial path; the second writer opens its
    # handle and grabs the lock during __init__, so the collision surfaces
    # at construction time rather than on first write.
    with pytest.raises(PersistenceError, match="another process"):
        SessionWriter(s)
    w1.close()


def test_lock_released_on_close_allows_reopen(
    _isolate_openrath_home: Path,
) -> None:
    s = Session(chunk_table=ChunkTable(rows=()))
    w1 = SessionWriter(s)
    w1.write_chunk(0, user_text_chunk("first"))
    w1.close()
    # After explicit close, reopening the same session id is allowed —
    # not a typical pattern, but it must not deadlock or false-fail.
    w2 = SessionWriter(s)
    w2.write_chunk(1, user_text_chunk("after close"))
    w2.close()


def test_lock_released_on_abandon_allows_reopen(
    _isolate_openrath_home: Path,
) -> None:
    s = Session(chunk_table=ChunkTable(rows=()))
    w1 = SessionWriter(s)
    w1.write_chunk(0, user_text_chunk("interrupted"))
    w1.abandon()
    w2 = SessionWriter(s)
    w2.write_chunk(1, user_text_chunk("after abandon"))
    w2.close()


def test_different_session_ids_dont_collide(_isolate_openrath_home: Path) -> None:
    s1 = Session(chunk_table=ChunkTable(rows=()))
    s2 = Session(chunk_table=ChunkTable(rows=()))
    w1 = SessionWriter(s1)
    w2 = SessionWriter(s2)
    w1.write_chunk(0, user_text_chunk("a"))
    w2.write_chunk(0, user_text_chunk("b"))
    w1.close()
    w2.close()
