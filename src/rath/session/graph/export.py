"""JSONL (newline-delimited JSON) export for session lineage graphs.

One Session per line. Edges are not materialized - ``parent_session_ids`` on
each row implies them - so the format is friendly to ``jq``, streaming
parsers, and naive Mermaid converters. Pair with
:class:`~rath.session.graph.LineageJournal` to dump only the sessions
visited inside a given block.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from rath.session.graph.recording import LineageJournal
from rath.session.manager import session_registry
from rath.session.session import Session

__all__ = [
    "session_to_jsonl_row",
    "export_jsonl_string",
    "export_jsonl",
    "export_journal_jsonl",
    "cumulative_usage_to_jsonable",
    "lineage_extras_to_jsonable",
]


def cumulative_usage_to_jsonable(session: Session) -> dict[str, int] | None:
    """Project ``session.cumulative_usage`` into a JSON-ready dict (or ``None``).

    Reads ``_cumulative_usage`` directly so persistence-layer callers running
    inside an in-flight materialization (where ``session._pending`` is still
    set) don't recursively trip :meth:`Session.synchronize` on themselves.
    """
    usage = session._cumulative_usage
    if usage is None:
        return None
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }


def lineage_extras_to_jsonable(
    extras: tuple[tuple[str, Any], ...],
) -> list[list[Any]]:
    """Convert ``lineage_extras`` into a JSONable list-of-pairs.

    Values that are not natively JSON-serializable are coerced to ``str(value)``
    so the row never fails to dump.
    """
    out: list[list[Any]] = []
    for key, value in extras:
        try:
            json.dumps(value)
            jvalue = value
        except (TypeError, ValueError):
            jvalue = str(value)
        out.append([str(key), jvalue])
    return out


def session_to_jsonl_row(session: Session) -> dict[str, Any]:
    """Project a :class:`Session` into a JSONable dict for one JSONL row."""
    return {
        "id": str(session.id),
        "parent_session_ids": [str(p) for p in session.parent_session_ids],
        "lineage_operator": session.lineage_operator,
        "lineage_kind": session.lineage_kind.value,
        "lineage_extras": lineage_extras_to_jsonable(session.lineage_extras),
        "chunk_count": len(session.chunk_table.rows),
        "cumulative_usage": cumulative_usage_to_jsonable(session),
    }


def export_jsonl_string(sessions: Iterable[Session]) -> str:
    """Return the JSONL text for ``sessions`` (one line per session, ``\\n``-terminated)."""
    parts: list[str] = []
    for s in sessions:
        parts.append(json.dumps(session_to_jsonl_row(s), ensure_ascii=False))
    return "\n".join(parts) + ("\n" if parts else "")


def export_jsonl(sessions: Iterable[Session], path: str | Path) -> None:
    """Write JSONL for ``sessions`` to ``path`` (UTF-8, ``\\n`` line endings)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = export_jsonl_string(sessions)
    p.write_text(text, encoding="utf-8")


def export_journal_jsonl(
    journal: LineageJournal,
    path: str | Path,
    *,
    skip_unknown: bool = True,
) -> None:
    """Resolve ``journal.visit_order`` through the session registry, then export.

    Sessions that are not in the global registry are silently skipped when
    ``skip_unknown`` is true (the default - this matches the typical use case
    where the journal outlives some sessions). Set ``skip_unknown=False`` to
    raise :class:`KeyError` instead.
    """
    reg = session_registry()
    rows: list[Session] = []
    for sid in journal.visit_order:
        s = reg.get(sid)
        if s is None:
            if skip_unknown:
                continue
            raise KeyError(f"session {sid} not in registry")
        rows.append(s)
    export_jsonl(rows, path)
