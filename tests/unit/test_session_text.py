"""``Session.text()`` returns the model's final answer.

This is the most common post-run operation; its absence is why the dynamic
Selector example reached for a non-existent ``session.text()``. The accessor
returns the last assistant message that carries text, skipping pure tool-call
turns, and ``None`` when there is no assistant text yet.
"""

from __future__ import annotations

from rath.session import Session
from rath.session.chunk import (
    ChunkTable,
    assistant_turn_chunk,
    user_text_chunk,
)


def _session(*rows: object) -> Session:
    return Session(chunk_table=ChunkTable(rows=tuple(rows)))  # type: ignore[arg-type]


def test_returns_last_assistant_text() -> None:
    sess = _session(
        user_text_chunk("hello"),
        assistant_turn_chunk(tool_calls=None, content="first"),
        user_text_chunk("more"),
        assistant_turn_chunk(tool_calls=None, content="final answer"),
    )
    assert sess.text() == "final answer"


def test_skips_trailing_pure_tool_call_turn() -> None:
    sess = _session(
        assistant_turn_chunk(tool_calls=None, content="the answer"),
        # A pure tool-call turn (no text) must not mask the real answer.
        assistant_turn_chunk(tool_calls=None, content=None),
    )
    assert sess.text() == "the answer"


def test_none_when_no_assistant_text() -> None:
    sess = _session(user_text_chunk("hi"))
    assert sess.text() is None


def test_empty_session_returns_none() -> None:
    assert _session().text() is None
