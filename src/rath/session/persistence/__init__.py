"""Append-only persistence for OpenRath sessions.

Stores each :class:`~rath.session.session.Session` as a JSONL file under
``.openrath/sessions/<uuid>.jsonl`` (resolved exactly like ``config.json`` —
see :mod:`rath.config.paths`). Designed for crash safety: every chunk is
flushed to disk as it lands, so a ``kill -9`` mid-loop loses at most the
last partial line.

Public surface:

* :class:`SessionWriter` — direct writer; also wired into
  :func:`~rath.session.loop.run_session_loop` via its ``persist=`` parameter.
* :func:`load_session` / :func:`list_persisted_sessions` — read side.
* :class:`PersistedSession` / :class:`PersistedSessionMeta` /
  :class:`PersistedSessionHeader` — round-trip dataclasses.
* :func:`delete_session` / :func:`prune_sessions` — GC helpers.
* :exc:`PersistenceError` — corrupt / unreadable file.
"""

from rath.session.persistence._migrations import (
    CURRENT_SCHEMA_VERSION,
    register_chunk_migration,
    register_header_migration,
)
from rath.session.persistence.errors import PersistenceError
from rath.session.persistence.loader import (
    PersistedSession,
    PersistedSessionHeader,
    PersistedSessionMeta,
    delete_session,
    list_persisted_sessions,
    load_session,
    prune_sessions,
)
from rath.session.persistence.paths import (
    SESSION_FILE_SUFFIX,
    SESSION_PARTIAL_SUFFIX,
    SESSIONS_DIR_NAME,
    ensure_sessions_dir,
    session_file,
    session_partial_file,
    sessions_dir,
)
from rath.session.persistence.writer import SessionWriter

__all__ = [
    # Errors
    "PersistenceError",
    # Writer
    "SessionWriter",
    # Loader + GC
    "PersistedSession",
    "PersistedSessionHeader",
    "PersistedSessionMeta",
    "load_session",
    "list_persisted_sessions",
    "delete_session",
    "prune_sessions",
    # Migrations
    "CURRENT_SCHEMA_VERSION",
    "register_header_migration",
    "register_chunk_migration",
    # Paths
    "SESSIONS_DIR_NAME",
    "SESSION_FILE_SUFFIX",
    "SESSION_PARTIAL_SUFFIX",
    "sessions_dir",
    "session_file",
    "session_partial_file",
    "ensure_sessions_dir",
]
