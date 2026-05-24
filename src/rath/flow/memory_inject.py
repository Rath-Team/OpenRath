"""Memory injection policies invoked by :class:`~rath.flow.agent.Agent.forward`.

A policy reads a :class:`~rath.session.session.Session` and a
:class:`~rath.memory.abc.MemoryStore`, then returns a tuple of
:class:`~rath.session.chunk.ChunkRow` to prepend to the next loop turn
(typically :attr:`ChunkKind.SYSTEM` notes that summarize relevant
recalled memories).

The injection step must NEVER raise into the session loop -- on store
errors or a closed store, return an empty tuple and log a warning so
the loop continues without recall.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from rath.memory.op_types import MemoryOpFind
from rath.memory.results import MemoryFindResult, MemoryHit
from rath.session.chunk import ChunkKind, ChunkRow
from rath.session.session import Session

__all__ = [
    "MemoryInjectionPolicy",
    "DefaultRecallInjection",
]


_LOG = logging.getLogger(__name__)


@runtime_checkable
class MemoryInjectionPolicy(Protocol):
    """Strategy object that turns a session + store into prepended chunks."""

    def inject(
        self, session: Session, store: "object"
    ) -> tuple[ChunkRow, ...]:  # pragma: no cover -- protocol body
        ...


@dataclass(frozen=True, slots=True)
class DefaultRecallInjection:
    """Find-based recall: take the last user message as query, prepend hit snippets.

    Configurable knobs:

    - ``top_k``: number of hits to request from the store.
    - ``target_uri``: optional scope, e.g. ``viking://user/memories/`` to
      limit recall to user-owned notes.
    - ``level``: hierarchical detail level expected on each hit; passed
      through informationally (most adapters return ``abstract`` in
      ``MemoryHit.snippet``).
    """

    top_k: int = 4
    target_uri: str | None = None
    level: Literal["abstract", "overview", "detail"] = "abstract"

    def inject(self, session: Session, store: "object") -> tuple[ChunkRow, ...]:
        # ``MemoryStore`` lives in a separate package; do a duck-typed check
        # against the public surface to avoid an import cycle.
        if getattr(store, "closed", True):
            _LOG.warning(
                "memory injection skipped: store is closed (%r)",
                getattr(store, "handle", store),
            )
            return ()

        last_user = _last_user_message(session)
        if last_user is None:
            return ()

        op = MemoryOpFind(
            query=last_user,
            target_uri=self.target_uri,
            top_k=self.top_k,
        )
        try:
            result = store.dispatch(op)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 -- recall must not break the loop
            _LOG.warning("memory injection dispatch failed: %s", exc)
            return ()

        if not isinstance(result, MemoryFindResult) or not result.hits:
            return ()

        return tuple(_hit_to_chunk(hit) for hit in result.hits)


def _last_user_message(session: Session) -> str | None:
    for row in reversed(session.chunk_table.rows):
        if row.kind == ChunkKind.USER:
            content = row.payload.get("content")
            if isinstance(content, str) and content.strip():
                return content
    return None


def _hit_to_chunk(hit: MemoryHit) -> ChunkRow:
    snippet = (hit.snippet or "").strip()
    body = f"[memory:{hit.uri}] {snippet}" if snippet else f"[memory:{hit.uri}]"
    return ChunkRow(kind=ChunkKind.SYSTEM, payload={"content": body})
