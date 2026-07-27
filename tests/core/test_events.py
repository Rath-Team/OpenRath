from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from rath.events import Event, EventKind, ProducerRef, SessionEventLog
from rath.security import Provenance, TrustLevel


def _event(*, session_id, sequence: int, payload=None) -> Event:  # type: ignore[no-untyped-def]
    return Event.create(
        session_id=session_id,
        sequence=sequence,
        kind=EventKind.MESSAGE_CREATED,
        payload=payload or {"content": "hello"},
        producer=ProducerRef(kind="user", id="user-1"),
        trust=TrustLevel.UNTRUSTED,
        provenance=Provenance(source_type="user", source_id="user-1"),
    )


def test_event_payload_is_deeply_immutable() -> None:
    session_id = uuid4()
    payload = {"parts": [{"text": "hello"}]}
    event = _event(session_id=session_id, sequence=1, payload=payload)

    payload["parts"][0]["text"] = "changed"

    assert event.payload["parts"][0]["text"] == "hello"  # type: ignore[index]
    with pytest.raises(TypeError):
        event.payload["new"] = True  # type: ignore[index]
    assert event.created_at.tzinfo is not None


def test_session_event_log_requires_monotonic_contiguous_sequence() -> None:
    session_id = uuid4()
    first = _event(session_id=session_id, sequence=1)
    third = _event(session_id=session_id, sequence=3)

    with pytest.raises(ValueError, match="contiguous"):
        SessionEventLog(id=session_id, events=(first, third))


def test_session_event_log_rejects_cross_session_event() -> None:
    session_id = uuid4()
    with pytest.raises(ValueError, match="session_id"):
        SessionEventLog(
            id=session_id,
            events=(_event(session_id=uuid4(), sequence=1),),
        )


def test_append_assigns_next_sequence_without_mutating_original() -> None:
    session_id = uuid4()
    log = SessionEventLog(id=session_id)
    updated = log.append(
        kind=EventKind.MESSAGE_CREATED,
        payload={"content": "hello"},
        producer=ProducerRef(kind="user", id="user-1"),
        trust=TrustLevel.UNTRUSTED,
        provenance=Provenance(source_type="user", source_id="user-1"),
    )

    assert log.events == ()
    assert updated.events[0].sequence == 1
    assert isinstance(updated.events[0].created_at, datetime)

