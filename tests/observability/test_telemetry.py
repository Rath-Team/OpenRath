from __future__ import annotations

from contextlib import contextmanager

from rath.context import TraceContext
from rath.observability import GuardedTelemetry, InMemoryTelemetry, redact


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
