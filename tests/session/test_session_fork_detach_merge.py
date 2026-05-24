"""Session.fork / detach / merge — chunk replication and sandbox sharing."""

from __future__ import annotations

import pytest

from rath.backend import get
from rath.llm.chat_response import RathLLMTokenUsage
from rath.session import (
    ChunkTable,
    LineageKind,
    Session,
    create_leaf_user,
    user_text_chunk,
)


def test_fork_shares_open_sandbox_handle() -> None:
    backend = get("local")
    sb = backend.open()
    s = Session.from_user_message("hi").bind_sandbox(sb)
    assert sb.refcount == 1
    f = s.fork()
    assert f.sandbox is sb
    assert sb.refcount == 2
    assert not sb.closed
    s.close_sandbox()
    assert not sb.closed
    f.close_sandbox()
    assert sb.closed


def test_fork_inherits_backend_target_without_open_handle() -> None:
    s = Session.from_user_message("x").to("local", spec=".")
    f = s.fork()
    assert s.sandbox is None
    assert f.sandbox is None
    assert f.sandbox_backend == "local"


def test_detach_shares_open_sandbox_handle() -> None:
    backend = get("local")
    sb = backend.open()
    s = Session.from_user_message("y").bind_sandbox(sb)
    assert sb.refcount == 1
    d = s.detach()
    assert d.sandbox is sb
    assert sb.refcount == 2
    assert not sb.closed
    s.close_sandbox()
    assert not sb.closed
    d.close_sandbox()
    assert sb.closed


def test_detach_same_backend_target_no_parent() -> None:
    s = create_leaf_user("y").to("local")
    d = s.detach()
    assert d.sandbox is None
    assert d.sandbox_backend == "local"
    assert d.parent_session_ids == ()


def test_fork_session_wraps_session_fork() -> None:
    from rath.session.primitives import fork_session

    base = create_leaf_user("w")
    f1 = base.fork()
    f2 = fork_session(base)
    assert f1.chunk_table.rows == f2.chunk_table.rows
    assert f1.parent_session_ids == f2.parent_session_ids


def test_merge_concatenates_chunks_in_order() -> None:
    a = Session(chunk_table=ChunkTable(rows=(user_text_chunk("alpha"),)))
    b = Session(chunk_table=ChunkTable(rows=(user_text_chunk("beta"),)))
    m = a.merge(b)
    assert m.chunk_table.rows == a.chunk_table.rows + b.chunk_table.rows
    assert [r.payload["content"] for r in m.chunk_table.rows] == ["alpha", "beta"]


def test_merge_unbound_sessions_yields_unbound_result() -> None:
    a = Session.from_user_message("a")
    b = Session.from_user_message("b")
    m = a.merge(b)
    assert m.sandbox is None
    assert m.sandbox_backend is None


def test_merge_shared_sandbox_bumps_refcount() -> None:
    backend = get("local")
    sb = backend.open()
    a = Session.from_user_message("a").bind_sandbox(sb)
    b = Session.from_user_message("b").bind_sandbox(sb)
    assert sb.refcount == 2
    m = a.merge(b)
    assert m.sandbox is sb
    assert sb.refcount == 3
    a.close_sandbox()
    b.close_sandbox()
    assert sb.refcount == 1
    assert not sb.closed
    m.close_sandbox()
    assert sb.closed


def test_merge_keeps_first_sandbox_when_other_differs() -> None:
    backend = get("local")
    sb_a = backend.open()
    sb_b = backend.open()
    a = Session.from_user_message("a").bind_sandbox(sb_a)
    b = Session.from_user_message("b").bind_sandbox(sb_b)
    try:
        m = a.merge(b)
        assert m.sandbox is sb_a
        # self.sandbox got an extra ref (1 from a, 1 from m == 2)
        assert sb_a.refcount == 2
        # other.sandbox is untouched — b still holds its sole reference
        assert sb_b.refcount == 1
        m.close_sandbox()
        assert sb_a.refcount == 1
        assert not sb_a.closed
    finally:
        a.close_sandbox()
        b.close_sandbox()


def test_merge_one_bound_one_unbound_keeps_bound_sandbox() -> None:
    backend = get("local")
    sb = backend.open()
    a = Session.from_user_message("a").bind_sandbox(sb)
    b = Session.from_user_message("b")
    try:
        m = a.merge(b)
        assert m.sandbox is sb
        assert sb.refcount == 2
        m.close_sandbox()
        assert sb.refcount == 1
    finally:
        a.close_sandbox()


def test_merge_unbound_first_bound_second_yields_unbound_result() -> None:
    backend = get("local")
    sb = backend.open()
    a = Session.from_user_message("a")
    b = Session.from_user_message("b").bind_sandbox(sb)
    try:
        m = a.merge(b)
        # self (a) was unbound, so merge result is unbound regardless of b
        assert m.sandbox is None
        # b keeps its own reference
        assert sb.refcount == 1
    finally:
        b.close_sandbox()


def test_merge_unbound_different_backends_raises() -> None:
    a = Session.from_user_message("a").to("local")
    b = Session.from_user_message("b")
    b.sandbox_backend = "opensandbox"
    with pytest.raises(ValueError, match="different backends"):
        a.merge(b)


def test_merge_sums_cumulative_usage() -> None:
    a = Session(
        chunk_table=ChunkTable(rows=(user_text_chunk("a"),)),
        cumulative_usage=RathLLMTokenUsage(
            prompt_tokens=10, completion_tokens=5, total_tokens=15
        ),
    )
    b = Session(
        chunk_table=ChunkTable(rows=(user_text_chunk("b"),)),
        cumulative_usage=RathLLMTokenUsage(
            prompt_tokens=20, completion_tokens=7, total_tokens=27
        ),
    )
    m = a.merge(b)
    assert m.cumulative_usage is not None
    assert m.cumulative_usage.prompt_tokens == 30
    assert m.cumulative_usage.completion_tokens == 12
    assert m.cumulative_usage.total_tokens == 42


def test_merge_usage_none_safe() -> None:
    a = Session(chunk_table=ChunkTable(rows=(user_text_chunk("a"),)))
    b = Session(
        chunk_table=ChunkTable(rows=(user_text_chunk("b"),)),
        cumulative_usage=RathLLMTokenUsage(
            prompt_tokens=3, completion_tokens=1, total_tokens=4
        ),
    )
    m_ab = a.merge(b)
    assert m_ab.cumulative_usage == b.cumulative_usage
    m_ba = b.merge(a)
    assert m_ba.cumulative_usage == b.cumulative_usage


def test_merge_lineage_parents_and_kind() -> None:
    a = create_leaf_user("a")
    b = create_leaf_user("b")
    m = a.merge(b)
    assert m.parent_session_ids == (a.id, b.id)
    assert m.lineage_kind is LineageKind.OP_MERGE
    assert m.lineage_operator == "Session.merge"
