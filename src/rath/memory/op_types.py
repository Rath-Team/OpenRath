"""Concrete :class:`MemoryOp` payload types dispatched through a memory backend.

Mirrors :mod:`rath.backend.tool_types` for the memory plane: every concrete op
is a frozen, slotted dataclass with value semantics (hashable, equality by
field values).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = [
    "MemoryOp",
    "MemoryOpWrite",
    "MemoryOpRead",
    "MemoryOpList",
    "MemoryOpTree",
    "MemoryOpFind",
    "MemoryOpSearch",
    "MemoryOpResource",
    "MemoryOpCommit",
]


class MemoryOp:
    """Marker root for memory-plane op payloads.

    Concrete subclasses are frozen dataclasses. The marker exists so backends
    can declare :meth:`~rath.memory.abc.MemoryBackend.supported_ops` and so
    the registry can refuse unknown subtypes.
    """

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class MemoryOpWrite(MemoryOp):
    """Update an existing memory entry at ``uri`` with free-form text content.

    OpenViking's ``write`` semantics are an *update* of an existing memory
    file (created by ``commit_session`` extraction or seeded via
    :class:`MemoryOpResource`); it is not a generic create-file path.
    """

    uri: str
    content: str
    mode: str = "replace"
    wait: bool = False
    timeout_seconds: float | None = None
    metadata: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class MemoryOpRead(MemoryOp):
    """Read the entry at ``uri`` at the requested hierarchical level."""

    uri: str
    level: Literal["abstract", "overview", "detail"] = "detail"
    encoding: str | None = "utf-8"


@dataclass(frozen=True, slots=True)
class MemoryOpList(MemoryOp):
    """List immediate entries under ``uri`` (non-recursive)."""

    uri: str


@dataclass(frozen=True, slots=True)
class MemoryOpTree(MemoryOp):
    """Recursively list entries under ``uri`` up to ``depth`` levels."""

    uri: str
    depth: int = 2


@dataclass(frozen=True, slots=True)
class MemoryOpFind(MemoryOp):
    """Direct semantic search; ``target_uri`` scopes the search namespace."""

    query: str
    target_uri: str | None = None
    top_k: int = 8


@dataclass(frozen=True, slots=True)
class MemoryOpSearch(MemoryOp):
    """Intent-aware search; ``session_id`` scopes ranking against a session."""

    query: str
    session_id: str | None = None
    target_uri: str | None = None
    top_k: int = 8


@dataclass(frozen=True, slots=True)
class MemoryOpResource(MemoryOp):
    """Register an external resource (URL / file / dir) for ingestion.

    ``target_uri`` is the destination directory under ``viking://resources/``.
    """

    source: str
    target_uri: str | None = None
    reason: str = ""
    instruction: str = ""
    wait: bool = True
    timeout_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class MemoryOpCommit(MemoryOp):
    """Commit a session's messages for archive + memory extraction.

    Each entry in ``messages`` is a ``{"role": ..., "content": ...}`` dict
    (or ``{"role": ..., "parts": [...]}`` for multipart messages).
    """

    session_id: str
    messages: Sequence[Any]
    used_uris: Sequence[str] = field(default_factory=tuple)
    wait: bool = False
    timeout_seconds: float | None = None
