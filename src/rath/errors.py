"""Stable machine-readable errors for OpenRath v2 public contracts."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any

from rath._json import JSONValue, freeze_mapping, thaw_json

__all__ = ["ErrorCode", "RathError"]


class ErrorCode(str, Enum):
    """Stable error identifiers; enum values are part of the public API."""

    INVALID_ARGUMENT = "request.invalid_argument"
    UNAUTHENTICATED = "security.unauthenticated"
    FORBIDDEN = "security.forbidden"
    APPROVAL_REQUIRED = "security.approval_required"
    POLICY_ERROR = "security.policy_error"
    CONFLICT = "resource.conflict"
    NOT_FOUND = "resource.not_found"
    DEADLINE_EXCEEDED = "runtime.deadline_exceeded"
    CANCELLED = "runtime.cancelled"
    UNAVAILABLE = "runtime.unavailable"
    INTERNAL = "internal.error"


class RathError(RuntimeError):
    """Base exception with a stable code and serialization contract."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool = False,
        details: Mapping[str, object] | None = None,
    ) -> None:
        if not message:
            raise ValueError("message must not be empty")
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = bool(retryable)
        self.details: Mapping[str, JSONValue] = freeze_mapping(
            details,
            field="details",
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the stable transport representation."""
        return {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
            "details": thaw_json(self.details),
        }
