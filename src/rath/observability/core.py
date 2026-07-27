"""Dependency-light OpenTelemetry-compatible tracing and metric hooks."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from rath._json import JSONValue, freeze_mapping
from rath.context import TraceContext

__all__ = [
    "InMemoryTelemetry",
    "NoOpTelemetry",
    "GuardedTelemetry",
    "SpanRecord",
    "Telemetry",
]


@dataclass(frozen=True, slots=True)
class SpanRecord:
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    started_at: datetime
    ended_at: datetime
    duration_ms: float
    status: str
    attributes: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attributes",
            freeze_mapping(self.attributes, field="span.attributes"),
        )


@runtime_checkable
class Telemetry(Protocol):
    @contextmanager
    def span(
        self,
        name: str,
        *,
        context: TraceContext,
        attributes: Mapping[str, object] | None = None,
    ) -> Iterator[None]: ...

    def increment(
        self,
        name: str,
        value: int = 1,
        *,
        attributes: Mapping[str, str] | None = None,
    ) -> None: ...


class NoOpTelemetry:
    @contextmanager
    def span(
        self,
        name: str,
        *,
        context: TraceContext,
        attributes: Mapping[str, object] | None = None,
    ) -> Iterator[None]:
        yield

    def increment(
        self,
        name: str,
        value: int = 1,
        *,
        attributes: Mapping[str, str] | None = None,
    ) -> None:
        return None


class InMemoryTelemetry:
    """Reference exporter used by tests and embedded diagnostics."""

    def __init__(self) -> None:
        self._spans: list[SpanRecord] = []
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], int] = {}
        self._lock = threading.Lock()

    @property
    def spans(self) -> tuple[SpanRecord, ...]:
        with self._lock:
            return tuple(self._spans)

    @property
    def counters(self) -> Mapping[tuple[str, tuple[tuple[str, str], ...]], int]:
        with self._lock:
            return dict(self._counters)

    @contextmanager
    def span(
        self,
        name: str,
        *,
        context: TraceContext,
        attributes: Mapping[str, object] | None = None,
    ) -> Iterator[None]:
        started_at = datetime.now(timezone.utc)
        started = time.perf_counter()
        status = "ok"
        try:
            yield
        except BaseException:
            status = "error"
            raise
        finally:
            ended_at = datetime.now(timezone.utc)
            record = SpanRecord(
                name=name,
                trace_id=context.trace_id,
                span_id=context.span_id,
                parent_span_id=None,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                status=status,
                attributes=freeze_mapping(attributes, field="span.attributes"),
            )
            with self._lock:
                self._spans.append(record)

    def increment(
        self,
        name: str,
        value: int = 1,
        *,
        attributes: Mapping[str, str] | None = None,
    ) -> None:
        labels = tuple(sorted((attributes or {}).items()))
        with self._lock:
            key = (name, labels)
            self._counters[key] = self._counters.get(key, 0) + value


class GuardedTelemetry:
    """Failure-isolating wrapper: exporter faults never change application results."""

    def __init__(self, delegate: Telemetry) -> None:
        self.delegate = delegate

    @contextmanager
    def span(
        self,
        name: str,
        *,
        context: TraceContext,
        attributes: Mapping[str, object] | None = None,
    ) -> Iterator[None]:
        manager = None
        try:
            manager = self.delegate.span(
                name,
                context=context,
                attributes=attributes,
            )
            manager.__enter__()
        except Exception:
            manager = None
        try:
            yield
        except BaseException as exc:
            if manager is not None:
                try:
                    manager.__exit__(type(exc), exc, exc.__traceback__)
                except Exception:
                    pass
            raise
        else:
            if manager is not None:
                try:
                    manager.__exit__(None, None, None)
                except Exception:
                    pass

    def increment(
        self,
        name: str,
        value: int = 1,
        *,
        attributes: Mapping[str, str] | None = None,
    ) -> None:
        try:
            self.delegate.increment(name, value, attributes=attributes)
        except Exception:
            pass
