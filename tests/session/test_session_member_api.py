"""Session member-function API: ``Session.create`` covers user/system/empty leaves."""

from __future__ import annotations

import pytest

from rath.session import LineageKind, Session
from rath.session.chunk import ChunkKind


def test_create_user_leaf_stamps_lineage_and_chunk() -> None:
    s = Session.create("user", "hello")
    assert len(s.chunk_table.rows) == 1
    row = s.chunk_table.rows[0]
    assert row.kind == ChunkKind.USER
    assert row.payload["content"] == "hello"
    assert s.parent_session_ids == ()
    assert s.lineage_kind is LineageKind.LEAF_USER
    assert s.lineage_operator == "Session.create"
    assert s.sandbox is None
    assert s.sandbox_backend is None


def test_create_system_leaf_stamps_lineage_and_chunk() -> None:
    s = Session.create("system", "you are helpful")
    assert len(s.chunk_table.rows) == 1
    row = s.chunk_table.rows[0]
    assert row.kind == ChunkKind.SYSTEM
    assert row.payload["content"] == "you are helpful"
    assert s.parent_session_ids == ()
    assert s.lineage_kind is LineageKind.LEAF_SYSTEM
    assert s.lineage_operator == "Session.create"


def test_create_empty_has_no_rows_and_no_lineage_stamp() -> None:
    s = Session.create("empty")
    assert s.chunk_table.rows == ()
    # "empty" intentionally skips LineageRecorder stamping; defaults remain.
    assert s.parent_session_ids == ()
    assert s.lineage_kind is LineageKind.UNKNOWN
    assert s.lineage_operator == "implicit"


def test_create_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="unknown kind"):
        Session.create("agent", "no")


def test_create_then_to_chains_for_local_backend() -> None:
    s = Session.create("user", "hi").to("local")
    assert s.sandbox_backend == "local"
    assert s.sandbox is None
    with s:
        assert s.sandbox is not None
        assert not s.sandbox.closed
    assert s.sandbox is None
