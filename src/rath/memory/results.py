"""Typed results returned from :meth:`~rath.memory.abc.MemoryBackend.dispatch`.

Mirrors :mod:`rath.backend.results`. :class:`MemoryExecutionFailure` validates
its ``kind`` field against a fixed set in ``__post_init__`` so adapters cannot
silently invent new failure kinds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "MemoryResult",
    "MemoryHit",
    "MemoryEntry",
    "MemoryFindResult",
    "MemoryReadResult",
    "MemoryListResult",
    "MemoryWriteResult",
    "MemoryCommitResult",
    "MemoryExecutionFailure",
]


_KNOWN_FAILURE_KINDS: frozenset[str] = frozenset(
    {
        "not_found",
        "unsupported",
        "transport",
        "extraction_failed",
        "store_closed",
        "unauthorized",
        "timeout",
        "invalid_uri",
        "internal",
    }
)


FailureKind = Literal[
    "not_found",
    "unsupported",
    "transport",
    "extraction_failed",
    "store_closed",
    "unauthorized",
    "timeout",
    "invalid_uri",
    "internal",
]


class MemoryResult:
    """Marker root for memory-plane dispatch results."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class MemoryHit:
    """One ranked hit returned by :class:`MemoryFindResult`."""

    uri: str
    score: float
    snippet: str | None = None
    level: Literal["abstract", "overview", "detail"] | None = None


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    """A single entry inside :class:`MemoryListResult`."""

    name: str
    uri: str
    is_dir: bool
    size: int | None = None


@dataclass(frozen=True, slots=True)
class MemoryFindResult(MemoryResult):
    """Result of :class:`~rath.memory.op_types.MemoryOpFind` / ``MemoryOpSearch``."""

    hits: tuple[MemoryHit, ...]


@dataclass(frozen=True, slots=True)
class MemoryReadResult(MemoryResult):
    """Result of :class:`~rath.memory.op_types.MemoryOpRead`.

    ``data`` is ``str`` when the op carried an ``encoding`` and the backend
    decoded the bytes; ``bytes`` when ``encoding=None``.
    """

    uri: str
    data: str | bytes
    level: Literal["abstract", "overview", "detail"]


@dataclass(frozen=True, slots=True)
class MemoryListResult(MemoryResult):
    """Result of :class:`~rath.memory.op_types.MemoryOpList` / ``MemoryOpTree``."""

    entries: tuple[MemoryEntry, ...]


@dataclass(frozen=True, slots=True)
class MemoryWriteResult(MemoryResult):
    """Result of :class:`~rath.memory.op_types.MemoryOpWrite`."""

    uri: str
    bytes_written: int


@dataclass(frozen=True, slots=True)
class MemoryCommitResult(MemoryResult):
    """Result of :class:`~rath.memory.op_types.MemoryOpCommit`.

    ``extracted_count`` is ``-1`` when the backend cannot report the count
    (e.g. ``wait=False`` async extraction).
    """

    task_id: str | None
    archived_uri: str | None
    extracted_count: int


@dataclass(frozen=True, slots=True)
class MemoryExecutionFailure(MemoryResult):
    """Structured failure surface for memory dispatch.

    ``kind`` must be one of :data:`_KNOWN_FAILURE_KINDS`; adapters route
    unexpected exceptions through ``kind="internal"``.
    """

    kind: FailureKind
    message: str
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in _KNOWN_FAILURE_KINDS:
            raise ValueError(
                f"MemoryExecutionFailure.kind={self.kind!r} not in "
                f"{sorted(_KNOWN_FAILURE_KINDS)}"
            )
