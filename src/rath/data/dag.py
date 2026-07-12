"""Export the Session lineage DAG as training data.

ATIF represents hierarchy — a parent embedding its subagents — but it has no
fork/merge graph. OpenRath's lineage does, and :class:`LineageKind` already
distinguishes ``OP_FORK``, ``OP_MERGE``, ``OP_DETACH``, and
``OP_SESSION_COMPRESS``. This is the structure no competing framework exports, so
it is exported losslessly here and interpreted nowhere else: what a branch *means*
is the consumer's call, not ours.

Traversal and cycle validation are not reimplemented; they already live in
:mod:`rath.session.graph.traverse`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rath.persistence import write_jsonl
from rath.session.graph.traverse import (
    edge_pairs,
    lineage_view_dataclass,
    validate_acyclic,
)
from rath.session.session import Session

__all__ = [
    "SESSION_GRAPH_SCHEMA_VERSION",
    "SessionEdge",
    "SessionGraph",
    "SessionNode",
    "build_session_graph",
    "write_session_graph_jsonl",
]

SESSION_GRAPH_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SessionNode:
    """One session in the lineage DAG, with whatever score it earned."""

    session_id: str
    lineage_kind: str
    lineage_operator: str | None
    reward: float | None = None
    status: str | None = None

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "schema_version": SESSION_GRAPH_SCHEMA_VERSION,
            "record_type": "session_node",
            "session_id": self.session_id,
            "lineage_kind": self.lineage_kind,
            "lineage_operator": self.lineage_operator,
            "reward": self.reward,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class SessionEdge:
    parent: str
    child: str

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "schema_version": SESSION_GRAPH_SCHEMA_VERSION,
            "record_type": "session_edge",
            "parent": self.parent,
            "child": self.child,
        }


@dataclass(frozen=True, slots=True)
class SessionGraph:
    nodes: tuple[SessionNode, ...] = ()
    edges: tuple[SessionEdge, ...] = ()

    def children_of(self, session_id: str) -> tuple[str, ...]:
        return tuple(edge.child for edge in self.edges if edge.parent == session_id)

    def records(self) -> tuple[Any, ...]:
        return (*self.nodes, *self.edges)


def build_session_graph(
    sessions: Iterable[Session],
    *,
    rewards: Mapping[str, float] | None = None,
    statuses: Mapping[str, str] | None = None,
) -> SessionGraph:
    """Project sessions into a validated lineage DAG.

    Raises :exc:`LineageConsistencyError` when a parent is missing or the graph
    cycles. A partial graph would silently drop branches, and a branch that
    vanishes without a word is worse than a build that fails loudly.
    """

    by_id = {session.id: session for session in sessions}
    validate_acyclic(by_id)

    reward_map = dict(rewards or {})
    status_map = dict(statuses or {})
    nodes = tuple(
        SessionNode(
            session_id=str(session_id),
            lineage_kind=lineage_view_dataclass(session).lineage_kind_str,
            lineage_operator=session.lineage_operator,
            reward=reward_map.get(str(session_id)),
            status=status_map.get(str(session_id)),
        )
        for session_id, session in by_id.items()
    )
    edges = tuple(
        SessionEdge(str(parent), str(child)) for parent, child in edge_pairs(by_id)
    )
    return SessionGraph(nodes, edges)


def write_session_graph_jsonl(graph: SessionGraph, path: str | Path) -> None:
    """Write the graph as JSONL: one line per node, then one line per edge."""

    write_jsonl(path, [record.to_jsonable() for record in graph.records()])
