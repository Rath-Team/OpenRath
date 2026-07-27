"""Durable Run, Checkpoint, Interrupt, and event state models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from rath._json import JSONValue, freeze_mapping
from rath.errors import ErrorCode, RathError

__all__ = [
    "ApprovalDecision",
    "ApprovalDecisionKind",
    "Checkpoint",
    "ConflictError",
    "Interrupt",
    "InterruptKind",
    "InvalidRunTransition",
    "Run",
    "RunEvent",
    "RunStatus",
    "assert_transition",
]


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    NEEDS_REVIEW = "needs_review"


TERMINAL_RUN_STATUSES = frozenset(
    {
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.TIMED_OUT,
    }
)

_TRANSITIONS: Mapping[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset(
        {
            RunStatus.RUNNING,
            RunStatus.CANCELLED,
            RunStatus.TIMED_OUT,
        }
    ),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.QUEUED,
            RunStatus.WAITING,
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.TIMED_OUT,
            RunStatus.NEEDS_REVIEW,
        }
    ),
    RunStatus.WAITING: frozenset(
        {
            RunStatus.QUEUED,
            RunStatus.CANCELLED,
            RunStatus.TIMED_OUT,
            RunStatus.FAILED,
        }
    ),
    RunStatus.NEEDS_REVIEW: frozenset(
        {
            RunStatus.QUEUED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.SUCCEEDED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
    RunStatus.TIMED_OUT: frozenset(),
}


class ConflictError(RathError):
    def __init__(self, message: str, *, details: Mapping[str, object] | None = None):
        super().__init__(
            ErrorCode.CONFLICT,
            message,
            retryable=False,
            details=details,
        )


class InvalidRunTransition(ConflictError):
    def __init__(self, source: RunStatus, target: RunStatus) -> None:
        super().__init__(
            f"invalid run transition from {source.value!r} to {target.value!r}",
            details={"source": source.value, "target": target.value},
        )
        self.source = source
        self.target = target


def assert_transition(source: RunStatus, target: RunStatus) -> None:
    if target not in _TRANSITIONS[source]:
        raise InvalidRunTransition(source, target)


def _aware(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Run:
    id: UUID
    plan_id: UUID
    revision_id: UUID
    session_id: UUID
    tenant_id: str
    status: RunStatus
    state: Mapping[str, JSONValue]
    next_nodes: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    version: int = 0
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("run tenant_id must not be empty")
        if self.version < 0:
            raise ValueError("run version must not be negative")
        _aware(self.created_at, field_name="run.created_at")
        _aware(self.updated_at, field_name="run.updated_at")
        object.__setattr__(self, "state", freeze_mapping(self.state, field="run.state"))
        object.__setattr__(self, "next_nodes", tuple(self.next_nodes))

    @classmethod
    def create(
        cls,
        *,
        plan_id: UUID,
        revision_id: UUID,
        session_id: UUID,
        tenant_id: str,
        status: RunStatus = RunStatus.QUEUED,
        state: Mapping[str, object] | None = None,
        next_nodes: tuple[str, ...] = (),
        idempotency_key: str | None = None,
        id: UUID | None = None,
    ) -> "Run":
        now = datetime.now(timezone.utc)
        return cls(
            id=id or uuid4(),
            plan_id=plan_id,
            revision_id=revision_id,
            session_id=session_id,
            tenant_id=tenant_id,
            status=status,
            state=freeze_mapping(state, field="run.state"),
            next_nodes=next_nodes,
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
        )


@dataclass(frozen=True, slots=True)
class RunEvent:
    run_id: UUID
    sequence: int
    type: str
    data: Mapping[str, JSONValue]
    created_at: datetime

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("run event sequence must be greater than zero")
        _aware(self.created_at, field_name="run_event.created_at")
        object.__setattr__(
            self,
            "data",
            freeze_mapping(self.data, field="run_event.data"),
        )


@dataclass(frozen=True, slots=True)
class Checkpoint:
    id: UUID
    run_id: UUID
    sequence: int
    plan_hash: str
    state: Mapping[str, JSONValue]
    next_nodes: tuple[str, ...]
    pending_interrupts: tuple[UUID, ...]
    effect_watermark: int
    created_at: datetime

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("checkpoint sequence must be greater than zero")
        if self.effect_watermark < 0:
            raise ValueError("effect_watermark must not be negative")
        if len(self.plan_hash) != 64:
            raise ValueError("plan_hash must be a SHA-256 hexadecimal digest")
        try:
            int(self.plan_hash, 16)
        except ValueError as exc:
            raise ValueError("plan_hash must be hexadecimal") from exc
        _aware(self.created_at, field_name="checkpoint.created_at")
        object.__setattr__(
            self,
            "state",
            freeze_mapping(self.state, field="checkpoint.state"),
        )
        object.__setattr__(self, "next_nodes", tuple(self.next_nodes))
        object.__setattr__(
            self,
            "pending_interrupts",
            tuple(self.pending_interrupts),
        )

    @classmethod
    def create(
        cls,
        *,
        run_id: UUID,
        sequence: int,
        plan_hash: str,
        state: Mapping[str, object],
        next_nodes: tuple[str, ...],
        effect_watermark: int,
        pending_interrupts: tuple[UUID, ...] = (),
    ) -> "Checkpoint":
        return cls(
            id=uuid4(),
            run_id=run_id,
            sequence=sequence,
            plan_hash=plan_hash,
            state=freeze_mapping(state, field="checkpoint.state"),
            next_nodes=next_nodes,
            pending_interrupts=pending_interrupts,
            effect_watermark=effect_watermark,
            created_at=datetime.now(timezone.utc),
        )


class InterruptKind(str, Enum):
    APPROVAL = "approval"
    INPUT = "input"
    REVIEW = "review"


class ApprovalDecisionKind(str, Enum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"
    RESPOND = "respond"


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    kind: ApprovalDecisionKind
    actor_id: str
    reason: str
    payload: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.actor_id.strip():
            raise ValueError("decision actor_id must not be empty")
        if not self.reason.strip():
            raise ValueError("decision reason must not be empty")
        object.__setattr__(
            self,
            "payload",
            freeze_mapping(self.payload, field="decision.payload"),
        )


@dataclass(frozen=True, slots=True)
class Interrupt:
    id: UUID
    run_id: UUID
    kind: InterruptKind
    request: Mapping[str, JSONValue]
    created_at: datetime
    decision: ApprovalDecision | None = None
    decided_at: datetime | None = None

    def __post_init__(self) -> None:
        _aware(self.created_at, field_name="interrupt.created_at")
        if self.decided_at is not None:
            _aware(self.decided_at, field_name="interrupt.decided_at")
        if (self.decision is None) != (self.decided_at is None):
            raise ValueError("decision and decided_at must be set together")
        object.__setattr__(
            self,
            "request",
            freeze_mapping(self.request, field="interrupt.request"),
        )

    @classmethod
    def create(
        cls,
        *,
        run_id: UUID,
        kind: InterruptKind,
        request: Mapping[str, object],
    ) -> "Interrupt":
        return cls(
            id=uuid4(),
            run_id=run_id,
            kind=kind,
            request=freeze_mapping(request, field="interrupt.request"),
            created_at=datetime.now(timezone.utc),
        )

