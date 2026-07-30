"""Recursive telemetry redaction with safe defaults."""

from __future__ import annotations

from collections.abc import Mapping

__all__ = ["redact"]

_SENSITIVE = frozenset(
    {"api_key", "authorization", "cookie", "password", "secret", "token"}
)


def redact(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): (
                "<redacted>"
                if any(part in str(key).lower() for part in _SENSITIVE)
                else redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value
