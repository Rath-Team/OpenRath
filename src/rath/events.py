"""Immutable session event and lineage-friendly event-log contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from rath._json import JSONValue, freeze_mapping
from rath.context import TraceContext
from rath.security import Provenance, TrustLevel

__all__ = [
    "Event",
    "EventKind",
    "ProducerRef",
    "SessionEventLog",
]


class EventKind(str, Enum):
    MESSAGE_CREATED = "session.message.created"
    SESSION_FORKED = "session.forked"
    SESSION_MERGED = "session.merged"
    RUN_STATE_CHANGED = "run.state.changed"
    NODE_STARTED = "run.node.started"
    NODE_COMPLETED = "run.node.completed"
    OUTPUT_DELTA = "run.output.delta"
    INTERRUPT_CREATED = "run.interrupt.created"
    TOOL_INVOCATION_CHANGED = "run.tool_invocation.changed"


@dataclass(frozen=True, slots=True)
class ProducerRef:
    kind: str
    id: str
    revision_id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise ValueError("producer kind must not be empty")
        if not self.id.strip():
            raise ValueError("producer id must not be empty")


@dataclass(frozen=True, slots=True)
class Event:
    """Deeply immutable event ordered within one Session."""

    id: UUID
    session_id: UUID
    sequence: int
    kind: EventKind
    payload: Mapping[str, JSONValue]
    producer: ProducerRef
    trust: TrustLevel
    provenance: Provenance
    created_at: datetime
    trace_context: TraceContext | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("event sequence must be greater than zero")
        if self.schema_version < 1:
            raise ValueError("event schema_version must be greater than zero")
        if self.created_at.tzinfo is None:
            raise ValueError("event created_at must be timezone-aware")
        object.__setattr__(
            self,
            "payload",
            freeze_mapping(self.payload, field="event.payload"),
        )

    @classmethod
    def create(
        cls,
        *,
        session_id: UUID,
        sequence: int,
        kind: EventKind,
        payload: Mapping[str, object],
        producer: ProducerRef,
        trust: TrustLevel,
        provenance: Provenance,
        trace_context: TraceContext | None = None,
    ) -> "Event":
        return cls(
            id=uuid4(),
            session_id=session_id,
            sequence=sequence,
            kind=kind,
            payload=freeze_mapping(payload, field="event.payload"),
            producer=producer,
            trust=trust,
            provenance=provenance,
            created_at=datetime.now(timezone.utc),
            trace_context=trace_context,
        )


@dataclass(frozen=True, slots=True)
class SessionEventLog:
    """Immutable ordered Event view; live runtime state is intentionally absent."""

    id: UUID = field(default_factory=uuid4)
    events: tuple[Event, ...] = ()
    parent_session_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        expected = 1
        for event in self.events:
            if event.session_id != self.id:
                raise ValueError("event session_id does not match event log id")
            if event.sequence != expected:
                raise ValueError("event sequence must be contiguous and start at 1")
            expected += 1
        if self.id in self.parent_session_ids:
            raise ValueError("session cannot be its own lineage parent")

    def append(
        self,
        *,
        kind: EventKind,
        payload: Mapping[str, object],
        producer: ProducerRef,
        trust: TrustLevel,
        provenance: Provenance,
        trace_context: TraceContext | None = None,
    ) -> "SessionEventLog":
        event = Event.create(
            session_id=self.id,
            sequence=len(self.events) + 1,
            kind=kind,
            payload=payload,
            producer=producer,
            trust=trust,
            provenance=provenance,
            trace_context=trace_context,
        )
        return SessionEventLog(
            id=self.id,
            events=(*self.events, event),
            parent_session_ids=self.parent_session_ids,
        )
