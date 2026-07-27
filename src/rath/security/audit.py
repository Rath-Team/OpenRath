"""Security audit events kept distinct from diagnostic traces."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID, uuid4

from rath._json import JSONValue, freeze_mapping
from rath.security.policy import Action, PolicyDecision, ResourceRef

if TYPE_CHECKING:
    from rath.context import RunContext

__all__ = [
    "AuditEvent",
    "AuditKind",
    "AuditSink",
    "InMemoryAuditSink",
]


class AuditKind(str, Enum):
    AUTHENTICATION = "authentication"
    POLICY_DECISION = "policy_decision"
    SECRET_RESOLUTION = "secret_resolution"
    TOOL_ACCESS = "tool_access"
    SANDBOX_ACCESS = "sandbox_access"
    MEMORY_ACCESS = "memory_access"
    RUN_CONTROL = "run_control"
    OPERATOR_OVERRIDE = "operator_override"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    id: UUID
    kind: AuditKind
    occurred_at: datetime
    tenant_id: str
    principal_id: str
    request_id: UUID
    trace_id: str
    action: str
    resource_kind: str
    resource_id: str
    outcome: str
    reason: str
    policy_id: str | None = None
    attributes: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None:
            raise ValueError("audit occurred_at must be timezone-aware")
        object.__setattr__(
            self,
            "attributes",
            freeze_mapping(self.attributes, field="audit.attributes"),
        )

    @classmethod
    def for_policy_decision(
        cls,
        *,
        kind: AuditKind,
        action: Action,
        resource: ResourceRef,
        context: RunContext,
        decision: PolicyDecision,
        attributes: Mapping[str, object] | None = None,
    ) -> "AuditEvent":
        return cls(
            id=uuid4(),
            kind=kind,
            occurred_at=datetime.now(timezone.utc),
            tenant_id=context.security.tenant_id,
            principal_id=context.security.principal.id,
            request_id=context.request_id,
            trace_id=context.trace_context.trace_id,
            action=action.name,
            resource_kind=resource.kind,
            resource_id=resource.id,
            outcome=decision.effect.value,
            reason=decision.reason,
            policy_id=decision.policy_id,
            attributes=freeze_mapping(attributes, field="audit.attributes"),
        )


@runtime_checkable
class AuditSink(Protocol):
    async def emit(self, event: AuditEvent) -> None: ...


class InMemoryAuditSink:
    """Deterministic reference sink for embedded mode and contract tests."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._lock = threading.Lock()

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        with self._lock:
            return tuple(self._events)

    async def emit(self, event: AuditEvent) -> None:
        with self._lock:
            self._events.append(event)
