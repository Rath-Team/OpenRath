"""Redacted newline-delimited JSON records for operational logging."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from datetime import datetime, timezone

from rath.context import TraceContext
from rath.observability.redaction import redact

__all__ = ["StructuredLogger"]


class StructuredLogger:
    """Emit stable JSON records without ever failing the application path."""

    def __init__(self, sink: Callable[[str], None] | None = None) -> None:
        self._sink = sink or logging.getLogger("openrath").info

    def emit(
        self,
        event: str,
        *,
        context: TraceContext | None = None,
        fields: Mapping[str, object] | None = None,
    ) -> None:
        record: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
        }
        if context is not None:
            record.update(
                {
                    "trace_id": context.trace_id,
                    "span_id": context.span_id,
                }
            )
        safe = redact(dict(fields or {}))
        assert isinstance(safe, dict)
        record.update(safe)
        try:
            self._sink(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )
            )
        except Exception:
            return
