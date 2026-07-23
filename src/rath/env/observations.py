"""Strict JSON projections of OpenRath Session state."""

from __future__ import annotations

import base64
import json
import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any
from uuid import UUID

from rath.session import ChunkKind, Session
from rath.session.graph.export import cumulative_usage_to_jsonable

__all__ = ["EnvObservation", "observation_from_session"]


def jsonable_value(value: Any, *, path: str = "$") -> Any:
    """Return an explicit JSON protocol value or reject unsupported input."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path}: non-finite float is not JSON-compatible")
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return {
            "__type__": "bytes",
            "base64": base64.b64encode(value).decode("ascii"),
        }
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path}: mapping keys must be strings")
            out[key] = jsonable_value(item, path=f"{path}.{key}")
        return out
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            jsonable_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise TypeError(f"{path}: unsupported protocol value {type(value).__name__}")


def _snapshot_mapping(
    value: Mapping[str, Any], *, field_name: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    copied = deepcopy(dict(value))
    jsonable_value(copied, path=field_name)
    return MappingProxyType(copied)


def _snapshot_chunks(chunks: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    projected = jsonable_value(list(chunks), path="chunks")
    assert isinstance(projected, list)
    return tuple(dict(item) for item in projected)


@dataclass(frozen=True, slots=True)
class EnvObservation:
    """Immutable, JSON-ready projection of one Session state."""

    session_id: str
    chunks: tuple[dict[str, Any], ...]
    latest_tool_result: dict[str, Any] | None
    sandbox_backend: str | None
    lineage: Mapping[str, Any]
    cumulative_usage: Mapping[str, int] | None

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, str) or not self.session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        object.__setattr__(self, "chunks", _snapshot_chunks(self.chunks))
        latest = self.latest_tool_result
        if latest is not None:
            projected = jsonable_value(latest, path="latest_tool_result")
            if not isinstance(projected, dict):
                raise TypeError("latest_tool_result must project to an object")
            object.__setattr__(self, "latest_tool_result", projected)
        object.__setattr__(
            self,
            "lineage",
            _snapshot_mapping(self.lineage, field_name="lineage"),
        )
        if self.cumulative_usage is not None:
            usage = _snapshot_mapping(
                self.cumulative_usage, field_name="cumulative_usage"
            )
            object.__setattr__(self, "cumulative_usage", usage)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "EnvObservation":
        chunks = raw.get("chunks", ())
        if not isinstance(chunks, Sequence) or isinstance(chunks, (str, bytes)):
            raise TypeError("EnvObservation chunks must be a sequence")
        lineage = raw.get("lineage", {})
        if not isinstance(lineage, Mapping):
            raise TypeError("EnvObservation lineage must be a mapping")
        latest = raw.get("latest_tool_result")
        if latest is not None and not isinstance(latest, Mapping):
            raise TypeError("EnvObservation latest_tool_result must be a mapping")
        usage = raw.get("cumulative_usage")
        if usage is not None and not isinstance(usage, Mapping):
            raise TypeError("EnvObservation cumulative_usage must be a mapping")
        decoded_chunks: list[dict[str, Any]] = []
        for index, item in enumerate(chunks):
            if not isinstance(item, Mapping):
                raise TypeError(f"EnvObservation chunk {index} must be a mapping")
            decoded_chunks.append(dict(item))
        return cls(
            session_id=str(raw.get("session_id", "")),
            chunks=tuple(decoded_chunks),
            latest_tool_result=None if latest is None else dict(latest),
            sandbox_backend=(
                None
                if raw.get("sandbox_backend") is None
                else str(raw["sandbox_backend"])
            ),
            lineage=dict(lineage),
            cumulative_usage=None if usage is None else dict(usage),
        )

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "chunks": jsonable_value(self.chunks, path="chunks"),
            "latest_tool_result": jsonable_value(
                self.latest_tool_result, path="latest_tool_result"
            ),
            "sandbox_backend": self.sandbox_backend,
            "lineage": jsonable_value(self.lineage, path="lineage"),
            "cumulative_usage": jsonable_value(
                self.cumulative_usage, path="cumulative_usage"
            ),
        }


def chunk_to_jsonable(row: Any) -> dict[str, Any]:
    payload = jsonable_value(row.payload, path="chunk.payload")
    assert isinstance(payload, dict)
    return {"kind": row.kind.value, "payload": payload}


def latest_tool_result_from_chunks(
    chunks: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    for chunk in reversed(chunks):
        if chunk.get("kind") != ChunkKind.TOOL_RESULT.value:
            continue
        payload = chunk.get("payload")
        if not isinstance(payload, Mapping):
            return None
        content = payload.get("content")
        content_json: Any = None
        if isinstance(content, str):
            try:
                content_json = json.loads(content)
            except json.JSONDecodeError:
                pass
        return {
            "tool_call_id": str(payload.get("tool_call_id", "")),
            "name": str(payload.get("name", "")),
            "content": str(content or ""),
            "content_json": jsonable_value(
                content_json, path="tool_result.content_json"
            ),
        }
    return None


def observation_from_session(session: Session) -> EnvObservation:
    chunks = tuple(chunk_to_jsonable(row) for row in session.chunk_table.rows)
    return EnvObservation(
        session_id=str(session.id),
        chunks=chunks,
        latest_tool_result=latest_tool_result_from_chunks(chunks),
        sandbox_backend=session.sandbox_backend,
        lineage={
            "parent_session_ids": [
                str(parent) for parent in session.parent_session_ids
            ],
            "lineage_operator": session.lineage_operator,
            "lineage_kind": session.lineage_kind.value,
            "lineage_extras": [
                [str(key), jsonable_value(value, path=f"lineage_extras.{key}")]
                for key, value in session.lineage_extras
            ],
        },
        cumulative_usage=cumulative_usage_to_jsonable(session),
    )
