"""Filesystem layout for persisted sessions.

All paths resolve under :func:`rath.config.resolve_config_dir`, so they share
the same ``OPENRATH_HOME`` → project marker → ``~/.openrath/`` resolution as
``config.json``. Sessions live under ``<config_dir>/sessions/<uuid>.jsonl``.

These functions are pure: they describe paths and (optionally) ``mkdir`` the
parent directory. No content is read or written here.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from rath.config.paths import resolve_config_dir

__all__ = [
    "SESSIONS_DIR_NAME",
    "SESSION_FILE_SUFFIX",
    "SESSION_PARTIAL_SUFFIX",
    "sessions_dir",
    "session_file",
    "session_partial_file",
    "ensure_sessions_dir",
]

SESSIONS_DIR_NAME = "sessions"
SESSION_FILE_SUFFIX = ".jsonl"
SESSION_PARTIAL_SUFFIX = ".jsonl.__partial__"


def sessions_dir() -> Path:
    """Return ``<resolved-config-dir>/sessions`` without creating it."""
    return resolve_config_dir() / SESSIONS_DIR_NAME


def session_file(session_id: UUID | str) -> Path:
    """Return the absolute path to ``sessions/<id>.jsonl``.

    Accepts either a :class:`uuid.UUID` or a string; both are normalized via
    ``str(id)`` so callers don't have to think about it.
    """
    return sessions_dir() / f"{session_id}{SESSION_FILE_SUFFIX}"


def session_partial_file(session_id: UUID | str) -> Path:
    """Return the WAL-style in-flight path ``sessions/<id>.jsonl.__partial__``.

    The writer opens this path on construction, appends header + chunks +
    trailer, and atomically renames to :func:`session_file` on graceful
    close. A leftover ``.__partial__`` file is the durable signal that the
    writing process crashed mid-session (or that the runtime drain timed
    out and abandoned the writer).
    """
    return sessions_dir() / f"{session_id}{SESSION_PARTIAL_SUFFIX}"


def ensure_sessions_dir() -> Path:
    """Create ``sessions/`` (and its parents) if missing; return the path."""
    target = sessions_dir()
    target.mkdir(parents=True, exist_ok=True)
    return target
