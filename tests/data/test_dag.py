from __future__ import annotations

from pathlib import Path

import pytest

from rath.data import build_session_graph, write_session_graph_jsonl
from rath.persistence import iter_jsonl
from rath.session import Session
from rath.session.graph import LineageKind


def test_a_fork_produces_two_edges_from_one_parent() -> None:
    parent = Session.from_user_message("root")
    left = parent.fork()
    right = parent.fork()

    graph = build_session_graph([parent, left, right])

    assert len(graph.nodes) == 3
    assert {edge.parent for edge in graph.edges} == {str(parent.id)}
    assert {edge.child for edge in graph.edges} == {str(left.id), str(right.id)}


def test_children_of_names_the_siblings() -> None:
    parent = Session.from_user_message("root")
    left = parent.fork()
    right = parent.fork()
    graph = build_session_graph([parent, left, right])
    assert set(graph.children_of(str(parent.id))) == {str(left.id), str(right.id)}


def test_fork_nodes_record_their_lineage_kind() -> None:
    parent = Session.from_user_message("root")
    child = parent.fork()
    graph = build_session_graph([parent, child])
    by_id = {node.session_id: node for node in graph.nodes}
    assert by_id[str(child.id)].lineage_kind == LineageKind.OP_FORK.value


def test_a_missing_parent_is_a_hard_error() -> None:
    parent = Session.from_user_message("root")
    child = parent.fork()
    # A partial graph silently drops branches, which is worse than failing.
    with pytest.raises(Exception):
        build_session_graph([child])


def test_rewards_and_statuses_attach_by_session_id() -> None:
    parent = Session.from_user_message("root")
    child = parent.fork()
    graph = build_session_graph(
        [parent, child],
        rewards={str(child.id): 1.5},
        statuses={str(child.id): "completed"},
    )
    by_id = {node.session_id: node for node in graph.nodes}
    assert by_id[str(child.id)].reward == 1.5
    assert by_id[str(child.id)].status == "completed"
    assert by_id[str(parent.id)].reward is None


def test_jsonl_round_trip(tmp_path: Path) -> None:
    parent = Session.from_user_message("root")
    child = parent.fork()
    path = tmp_path / "graph.jsonl"
    write_session_graph_jsonl(build_session_graph([parent, child]), path)

    kinds = [row["record_type"] for _, row in iter_jsonl(path)]
    assert kinds.count("session_node") == 2
    assert kinds.count("session_edge") == 1
