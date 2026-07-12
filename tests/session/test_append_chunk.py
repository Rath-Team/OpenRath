from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast

import pytest

from rath.session import Session, session_registry, user_text_chunk


def test_append_chunk_to_empty_session_returns_zero_based_index() -> None:
    session = Session.create("empty")
    assert session.append_chunk(user_text_chunk("first")) == 0
    assert session.chunk_table.rows == (user_text_chunk("first"),)


def test_append_chunk_preserves_sequential_order() -> None:
    session = Session.create("empty")
    assert session.append_chunk(user_text_chunk("a")) == 0
    assert session.append_chunk(user_text_chunk("b")) == 1
    assert [row.payload["content"] for row in session.chunk_table.rows] == ["a", "b"]


def test_append_chunk_is_thread_safe() -> None:
    session = Session.create("empty")
    with ThreadPoolExecutor(max_workers=8) as pool:
        assigned = list(
            pool.map(
                lambda value: session.append_chunk(user_text_chunk(str(value))),
                range(100),
            )
        )
    assert sorted(assigned) == list(range(100))
    assert len(session.chunk_table.rows) == 100
    assert {row.payload["content"] for row in session.chunk_table.rows} == {
        str(i) for i in range(100)
    }


def test_append_chunk_does_not_touch_registry() -> None:
    registry = session_registry()
    before = registry.get_active_id()
    session = Session.create("empty")
    session.append_chunk(user_text_chunk("row"))
    assert registry.get_active_id() == before
    assert registry.get(session.id) is None


def test_append_chunk_rejects_live_lazy_materialization() -> None:
    session = Session.create("empty")
    session._pending = cast(Any, object())
    with pytest.raises(RuntimeError, match="lazy materialization"):
        session.append_chunk(user_text_chunk("row"))
