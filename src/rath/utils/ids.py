"""Identifier normalization helpers for filesystem-backed persistence."""

from __future__ import annotations

from uuid import UUID

__all__ = ["coerce_uuid_str"]


def coerce_uuid_str(value: UUID | str, *, field: str = "id") -> str:
    """Return ``value`` as a canonical UUID string or raise ``ValueError``.

    Persistence identifiers are used as path components. Accepting arbitrary
    strings here would make path traversal possible, so string inputs must be
    parseable UUIDs before they can reach filesystem helpers.
    """

    if isinstance(value, UUID):
        return str(value)
    try:
        return str(UUID(str(value)))
    except ValueError as exc:
        raise ValueError(f"{field} must be a UUID") from exc
