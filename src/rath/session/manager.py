"""Process-wide registry of live :class:`~rath.session.Session` instances."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from uuid import UUID
from weakref import WeakValueDictionary

from rath.session.session import Session


@dataclass
class SessionRegistry:
    """Maps session ids to instances and records which session is active.

    The id->instance map holds **weak** references: a session is evicted
    automatically once no other reference keeps it alive. Without this a
    long-running process leaks every session (and its full transcript)
    forever, since each loop registers three of them per turn and there is
    no eviction path. ``get`` already returns ``None`` for absent ids, so a
    collected session reads as "unknown", which is the intended contract.
    """

    _by_id: "WeakValueDictionary[UUID, Session]" = field(
        default_factory=WeakValueDictionary
    )
    _active_id: UUID | None = None
    _lock: Lock = field(default_factory=Lock)

    def register(self, session: Session) -> None:
        with self._lock:
            self._by_id[session.id] = session

    def get(self, session_id: UUID) -> Session | None:
        with self._lock:
            return self._by_id.get(session_id)

    def set_active(self, session: Session | None) -> None:
        with self._lock:
            self._active_id = None if session is None else session.id

    def get_active_id(self) -> UUID | None:
        with self._lock:
            return self._active_id


_GLOBAL = SessionRegistry()


def session_registry() -> SessionRegistry:
    return _GLOBAL


__all__ = ["SessionRegistry", "session_registry"]
