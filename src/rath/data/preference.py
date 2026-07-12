"""Turn forked siblings into preference pairs.

Two branches forked from one parent saw exactly the same state and then diverged.
Their reward gap is the only comparison in the system that is not confounded by a
different starting point, which is what makes this the one extractor worth
building — and why branches of *different* parents are never paired.

This is deliberately the only extractor. Linearizing search-and-backtrack traces
and reconstructing multi-agent provenance are both possible from the exported DAG,
but no consumer has asked for either yet, and an abstraction built for an unknown
consumer is waste. They ship as example recipes instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from rath.data.dag import SessionGraph

__all__ = ["PreferencePair", "extract_preference_pairs"]


@dataclass(frozen=True, slots=True)
class PreferencePair:
    """One ``chosen`` over ``rejected`` comparison, both forked from one parent."""

    parent_session_id: str
    chosen: str
    rejected: str
    margin: float


def extract_preference_pairs(
    graph: SessionGraph,
    *,
    min_margin: float = 0.0,
) -> tuple[PreferencePair, ...]:
    """Pair scored siblings of a common parent, higher reward as ``chosen``.

    Branches without a reward are skipped: an unscored branch is not evidence of
    anything. Pairs at or below ``min_margin`` are dropped, since a reward gap
    inside the noise floor is not a preference.
    """

    reward_of = {node.session_id: node.reward for node in graph.nodes}
    by_parent: dict[str, list[str]] = {}
    for edge in graph.edges:
        by_parent.setdefault(edge.parent, []).append(edge.child)

    pairs: list[PreferencePair] = []
    for parent, children in by_parent.items():
        scored = sorted(child for child in children if reward_of.get(child) is not None)
        for left, right in combinations(scored, 2):
            left_reward = reward_of[left]
            right_reward = reward_of[right]
            assert left_reward is not None and right_reward is not None
            margin = abs(left_reward - right_reward)
            if margin <= min_margin:
                continue
            chosen, rejected = (
                (left, right) if left_reward > right_reward else (right, left)
            )
            pairs.append(PreferencePair(parent, chosen, rejected, margin))
    return tuple(pairs)
