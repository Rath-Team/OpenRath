"""Errors shared by OpenRath persistence helpers."""

from __future__ import annotations

__all__ = ["PersistenceError"]


class PersistenceError(RuntimeError):
    """Raised when persisted data is corrupt, unreadable, or locked."""
