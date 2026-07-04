"""Chunk rows for conversation content on each Session."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, cast, overload

from rath.llm import RathLLMMessage, RathLLMToolCallPart


class ChunkKind(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_RESULT = "tool_result"


@dataclass(frozen=True, slots=True)
class ChunkRow:
    """Immutable row in chronological order."""

    kind: ChunkKind
    payload: dict[str, Any]


def user_text_chunk(text: str) -> ChunkRow:
    """User message row for :attr:`ChunkKind.USER`."""
    return ChunkRow(kind=ChunkKind.USER, payload={"content": text})


def system_text_chunk(text: str) -> ChunkRow:
    """System prompt row for :attr:`ChunkKind.SYSTEM`."""
    return ChunkRow(kind=ChunkKind.SYSTEM, payload={"content": text})


def assistant_turn_chunk(
    *,
    tool_calls: tuple[RathLLMToolCallPart, ...] | None,
    content: str | None = None,
) -> ChunkRow:
    """Assistant message row; ``tool_calls`` are stored in OpenAI-style wire form."""
    wire: list[dict[str, Any]] | None = None
    if tool_calls:
        wire = []
        for p in tool_calls:
            wire.append(
                {
                    "id": p.id,
                    "type": p.type,
                    "function": {
                        "name": p.function.name,
                        "arguments": p.function.arguments,
                    },
                }
            )
    return ChunkRow(
        kind=ChunkKind.ASSISTANT,
        payload={"content": content, "tool_calls": wire},
    )


def tool_feedback_chunk(tool_call_id: str, name: str, body: str) -> ChunkRow:
    """Tool result chunk for replay into the chat transcript."""
    return ChunkRow(
        kind=ChunkKind.TOOL_RESULT,
        payload={"tool_call_id": tool_call_id, "name": name, "content": body},
    )


@dataclass(frozen=True, slots=True)
class ChunkTable:
    """Append-only chronological chunk list."""

    rows: tuple[ChunkRow, ...] = ()

    def __len__(self) -> int:
        return len(self.rows)

    @overload
    def __getitem__(self, index: int) -> ChunkRow: ...
    @overload
    def __getitem__(self, index: slice) -> tuple[ChunkRow, ...]: ...
    def __getitem__(self, index: int | slice) -> ChunkRow | tuple[ChunkRow, ...]:
        return self.rows[index]

    def __iter__(self) -> Iterator[ChunkRow]:
        return iter(self.rows)

    def extend(self, *additional: ChunkRow) -> ChunkTable:
        return ChunkTable(rows=self.rows + tuple(additional))


def _preview_brief(s: str, *, max_chars: int = 256) -> str:
    """Truncate long single-line previews (for logging / chunk hooks)."""

    if not s:
        return ""
    t = s.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
    if max_chars <= 8 or len(t) <= max_chars:
        return t
    edge = max(1, (max_chars - 5) // 2)
    return f"{t[:edge]} ... {t[-edge:]}"


def _tool_result_body_preview(raw: str, *, max_chars: int) -> str:
    """Decode JSON tool payloads and re-encode with real Unicode (not ``\\u`` escapes)."""

    t = raw.strip()
    if not t:
        return ""
    try:
        parsed: Any = json.loads(t)
    except json.JSONDecodeError:
        return _preview_brief(raw, max_chars=max_chars)
    try:
        normalized = json.dumps(
            parsed,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        return _preview_brief(raw, max_chars=max_chars)
    return _preview_brief(normalized, max_chars=max_chars)


def format_chunk_row_brief(index: int, row: ChunkRow, *, max_payload: int = 400) -> str:
    """Single-line description of one chunk row (debugging / logging helper)."""

    kind = row.kind.value
    p = row.payload
    if row.kind in (ChunkKind.SYSTEM, ChunkKind.USER):
        body = _preview_brief(str(p.get("content", "")), max_chars=max_payload)
        return f"[{index}] {kind}: {body!r}"
    if row.kind == ChunkKind.ASSISTANT:
        parts: list[str] = []
        c = p.get("content")
        if c is not None and str(c).strip():
            parts.append(f"text={_preview_brief(str(c), max_chars=max_payload)!r}")
        tc_raw = p.get("tool_calls") or []
        if tc_raw:
            names: list[str] = []
            for d in tc_raw:
                fn = d.get("function") or {}
                names.append(str(fn.get("name", "?")))
            parts.append(f"tools=[{', '.join(names)}]")
        summary = ", ".join(parts) if parts else "(empty)"
        return f"[{index}] {kind}: {summary}"
    if row.kind == ChunkKind.TOOL_RESULT:
        name = str(p.get("name", ""))
        body = _tool_result_body_preview(
            str(p.get("content", "")), max_chars=max_payload
        )
        return f"[{index}] {kind}: name={name!r} body={body}"
    return f"[{index}] {kind}: {p!r}"


def chunk_table_to_messages(tab: ChunkTable) -> tuple[RathLLMMessage, ...]:
    """Flatten chunk history into Rath LLM wire messages."""

    msgs: list[RathLLMMessage] = []
    for row in tab.rows:
        k = row.kind
        p = row.payload
        if k == ChunkKind.SYSTEM:
            msgs.append(RathLLMMessage(role="system", content=str(p["content"])))
        elif k == ChunkKind.USER:
            msgs.append(RathLLMMessage(role="user", content=str(p["content"])))
        elif k == ChunkKind.ASSISTANT:
            content_val = p.get("content")
            content = None if content_val is None else str(content_val)
            tc_raw = p.get("tool_calls")
            tc_tuple: tuple[Mapping[str, Any], ...] | None = None
            if tc_raw:
                lst = [cast(Mapping[str, Any], dict(d)) for d in tc_raw]
                tc_tuple = tuple(lst)
            msgs.append(
                RathLLMMessage(
                    role="assistant",
                    content=content,
                    tool_calls=tc_tuple,
                )
            )
        elif k == ChunkKind.TOOL_RESULT:
            msgs.append(
                RathLLMMessage(
                    role="tool",
                    content=str(p["content"]),
                    tool_call_id=str(p["tool_call_id"]),
                )
            )
    return tuple(msgs)
