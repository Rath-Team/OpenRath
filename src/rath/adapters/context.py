"""Uniform request context propagated to every external adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from rath.context import TraceContext
from rath.security import PolicyConstraints

__all__ = ["AdapterRequestContext"]


@dataclass(frozen=True, slots=True)
class AdapterRequestContext:
    run_id: UUID
    node_id: str
    tenant_id: str
    deadline: datetime | None
    trace_context: TraceContext
    idempotency_key: str | None
    policy_constraints: PolicyConstraints

    def __post_init__(self) -> None:
        if not self.node_id.strip():
            raise ValueError("adapter node_id must not be empty")
        if not self.tenant_id.strip():
            raise ValueError("adapter tenant_id must not be empty")
        if self.deadline is not None and self.deadline.tzinfo is None:
            raise ValueError("adapter deadline must be timezone-aware")

