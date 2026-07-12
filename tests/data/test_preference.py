from __future__ import annotations

from rath.data import (
    PreferencePair,
    SessionEdge,
    SessionGraph,
    SessionNode,
    extract_preference_pairs,
)


def _graph(*scored: tuple[str, float | None]) -> SessionGraph:
    nodes = [SessionNode("root", "leaf_user", None)]
    edges = []
    for session_id, reward in scored:
        nodes.append(SessionNode(session_id, "op_fork", "fork", reward=reward))
        edges.append(SessionEdge("root", session_id))
    return SessionGraph(tuple(nodes), tuple(edges))


def test_siblings_become_a_chosen_rejected_pair() -> None:
    pairs = extract_preference_pairs(_graph(("good", 1.0), ("bad", 0.0)))
    assert pairs == (
        PreferencePair(
            parent_session_id="root", chosen="good", rejected="bad", margin=1.0
        ),
    )


def test_equal_rewards_produce_no_pair() -> None:
    assert extract_preference_pairs(_graph(("a", 0.5), ("b", 0.5))) == ()


def test_margin_threshold_filters_weak_pairs() -> None:
    graph = _graph(("a", 1.0), ("b", 0.9))
    assert extract_preference_pairs(graph, min_margin=0.5) == ()
    assert len(extract_preference_pairs(graph, min_margin=0.05)) == 1


def test_unscored_branches_are_ignored() -> None:
    assert extract_preference_pairs(_graph(("a", 1.0), ("b", None))) == ()


def test_three_siblings_produce_every_ordered_pair() -> None:
    pairs = extract_preference_pairs(_graph(("a", 2.0), ("b", 1.0), ("c", 0.0)))
    assert {(pair.chosen, pair.rejected) for pair in pairs} == {
        ("a", "b"),
        ("a", "c"),
        ("b", "c"),
    }


def test_non_siblings_are_never_paired() -> None:
    # Two branches from different parents did not see the same state, so their
    # reward gap is confounded and means nothing.
    graph = SessionGraph(
        (
            SessionNode("r1", "leaf_user", None),
            SessionNode("r2", "leaf_user", None),
            SessionNode("a", "op_fork", "fork", reward=1.0),
            SessionNode("b", "op_fork", "fork", reward=0.0),
        ),
        (SessionEdge("r1", "a"), SessionEdge("r2", "b")),
    )
    assert extract_preference_pairs(graph) == ()
