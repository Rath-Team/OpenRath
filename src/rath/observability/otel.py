"""OpenTelemetry SDK bridge with W3C trace correlation."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from rath.context import TraceContext
from rath.observability.redaction import redact

__all__ = ["OpenTelemetry"]


class OpenTelemetry:
    """Telemetry implementation backed by configured OpenTelemetry providers."""

    def __init__(
        self,
        *,
        service_name: str = "openrath",
        tracer_provider: Any | None = None,
        meter_provider: Any | None = None,
    ) -> None:
        try:
            from opentelemetry import metrics, trace
        except ImportError as exc:
            raise RuntimeError(
                "OpenTelemetry support requires `pip install openrath[otel]`"
            ) from exc
        self._trace = trace
        self._tracer = trace.get_tracer(service_name, tracer_provider=tracer_provider)
        self._meter = metrics.get_meter(service_name, meter_provider=meter_provider)
        self._counters: dict[str, Any] = {}

    @contextmanager
    def span(
        self,
        name: str,
        *,
        context: TraceContext,
        attributes: Mapping[str, object] | None = None,
    ) -> Iterator[None]:
        trace = self._trace
        parent = trace.NonRecordingSpan(
            trace.SpanContext(
                trace_id=int(context.trace_id, 16),
                span_id=int(context.span_id, 16),
                is_remote=True,
                trace_flags=trace.TraceFlags(
                    trace.TraceFlags.SAMPLED
                    if context.sampled
                    else trace.TraceFlags.DEFAULT
                ),
                trace_state=trace.TraceState(),
            )
        )
        parent_context = trace.set_span_in_context(parent)
        safe = redact(dict(attributes or {}))
        assert isinstance(safe, dict)
        scalar_attributes = {
            key: value
            for key, value in safe.items()
            if isinstance(value, (bool, str, int, float))
        }
        with self._tracer.start_as_current_span(
            name,
            context=parent_context,
            attributes=scalar_attributes,
        ):
            yield

    def increment(
        self,
        name: str,
        value: int = 1,
        *,
        attributes: Mapping[str, str] | None = None,
    ) -> None:
        counter = self._counters.get(name)
        if counter is None:
            counter = self._meter.create_counter(name)
            self._counters[name] = counter
        counter.add(value, attributes=dict(attributes or {}))
