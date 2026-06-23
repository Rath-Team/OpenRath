"""The global session registry must not pin sessions forever.

Each loop turn registers three sessions; with a plain dict and no eviction
path a long-running process leaks every session and its full transcript.
The registry holds weak references, so a session is collected once no other
strong reference remains.
"""

from __future__ import annotations

import gc

from rath.session import Session
from rath.session.manager import SessionRegistry


def test_registry_evicts_unreferenced_session() -> None:
    reg = SessionRegistry()
    session = Session.from_user_message("hi")
    sid = session.id
    reg.register(session)
    assert reg.get(sid) is session

    del session
    gc.collect()

    assert reg.get(sid) is None


def test_registry_keeps_live_session() -> None:
    reg = SessionRegistry()
    session = Session.from_user_message("hi")
    reg.register(session)
    gc.collect()
    # Still strongly referenced here -> must survive collection.
    assert reg.get(session.id) is session


def test_active_id_does_not_pin_session() -> None:
    reg = SessionRegistry()
    session = Session.from_user_message("hi")
    sid = session.id
    reg.register(session)
    reg.set_active(session)

    del session
    gc.collect()

    # The active *id* is retained (a UUID), but it must not keep the
    # session instance alive.
    assert reg.get_active_id() == sid
    assert reg.get(sid) is None
