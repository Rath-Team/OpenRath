"""Request, trace, and durable run context contracts."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from rath.errors import ErrorCode, RathError
from rath.security.context import SecurityContext

__all__ = [
    "DeadlineExceededError",
    "RunContext",
    "TraceContext",
]


def _validate_hex(value: str, *, length: int, field_name: str) -> str:
    normalized = value.lower()
    if len(normalized) != length:
        raise ValueError(f"{field_name} must contain {length} hexadecimal characters")
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be hexadecimal") from exc
    return normalized


@dataclass(frozen=True, slots=True)
class TraceContext:
    """Minimal W3C-compatible trace correlation identifiers."""

    trace_id: str
    span_id: str
    sampled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "trace_id",
            _validate_hex(self.trace_id, length=32, field_name="trace_id"),
        )
        object.__setattr__(
            self,
            "span_id",
            _validate_hex(self.span_id, length=16, field_name="span_id"),
        )

    @classmethod
    def new(cls, *, sampled: bool = True) -> "TraceContext":
        return cls(
            trace_id=secrets.token_hex(16),
            span_id=secrets.token_hex(8),
            sampled=sampled,
        )


class DeadlineExceededError(RathError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.DEADLINE_EXCEEDED,
            "run deadline has been exceeded",
            retryable=False,
        )


@dataclass(frozen=True, slots=True)
class RunContext:
    """Explicit context propagated through runtime and adapter calls."""

    security: SecurityContext
    revision_id: UUID
    request_id: UUID = field(default_factory=uuid4)
    trace_context: TraceContext = field(default_factory=TraceContext.new)
    deadline: datetime | None = None

    def __post_init__(self) -> None:
        if self.deadline is not None and self.deadline.tzinfo is None:
            raise ValueError("deadline must be timezone-aware")

    @classmethod
    def local(
        cls,
        *,
        revision_id: UUID,
        deadline: datetime | None = None,
    ) -> "RunContext":
        return cls(
            security=SecurityContext.local(),
            revision_id=revision_id,
            deadline=deadline,
        )

    def remaining_seconds(self, *, now: datetime | None = None) -> float | None:
        if self.deadline is None:
            return None
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        return max(0.0, (self.deadline - current).total_seconds())

    def ensure_active(self, *, now: datetime | None = None) -> None:
        remaining = self.remaining_seconds(now=now)
        if remaining is not None and remaining <= 0:
            raise DeadlineExceededError()

