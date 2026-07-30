from __future__ import annotations

from contextlib import contextmanager

from rath.context import TraceContext
from rath.observability import (
    GuardedTelemetry,
    InMemoryTelemetry,
    OpenTelemetry,
    StructuredLogger,
    redact,
)


def test_span_records_status_and_correlation() -> None:
    telemetry = InMemoryTelemetry()
    trace = TraceContext.new()
    with telemetry.span("run", context=trace, attributes={"run.status": "running"}):
        pass
    assert telemetry.spans[0].trace_id == trace.trace_id
    assert telemetry.spans[0].status == "ok"


def test_redaction_is_recursive() -> None:
    assert redact({"api_key": "x", "nested": {"password": "y"}}) == {
        "api_key": "<redacted>",
        "nested": {"password": "<redacted>"},
    }


def test_guarded_telemetry_swallows_exporter_failure() -> None:
    class Broken:
        @contextmanager
        def span(self, name, *, context, attributes=None):  # type: ignore[no-untyped-def]
            yield
            raise RuntimeError("export failed")

        def increment(self, name, value=1, *, attributes=None):  # type: ignore[no-untyped-def]
            raise RuntimeError("export failed")

    guarded = GuardedTelemetry(Broken())
    with guarded.span("run", context=TraceContext.new()):
        value = 42
    guarded.increment("counter")
    assert value == 42


def test_otel_bridge_preserves_parent_trace_and_redacts_secrets() -> None:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    telemetry = OpenTelemetry(tracer_provider=provider)
    context = TraceContext.new()
    with telemetry.span(
        "openrath.run",
        context=context,
        attributes={"run_id": "r1", "api_key": "secret"},
    ):
        pass

    span = exporter.get_finished_spans()[0]
    assert f"{span.context.trace_id:032x}" == context.trace_id
    assert span.attributes["api_key"] == "<redacted>"


def test_structured_logger_correlates_and_redacts() -> None:
    import json

    records: list[str] = []
    trace = TraceContext.new()
    logger = StructuredLogger(records.append)
    logger.emit(
        "run.failed",
        context=trace,
        fields={"run_id": "run-1", "api_key": "secret"},
    )

    parsed = json.loads(records[0])
    assert parsed["event"] == "run.failed"
    assert parsed["trace_id"] == trace.trace_id
    assert parsed["run_id"] == "run-1"
    assert parsed["api_key"] == "<redacted>"
