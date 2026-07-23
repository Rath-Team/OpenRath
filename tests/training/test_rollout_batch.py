from __future__ import annotations

from dataclasses import replace

import pytest

from rath.env import (
    EnvObservation,
    ToolAction,
    TrajectoryEpisode,
    TrajectoryEpisodeEnd,
    TrajectoryEpisodeStart,
    TrajectoryStep,
)
from rath.training import (
    EpisodeRollout,
    RolloutBatch,
    RolloutEpisode,
    TrainingBatchError,
)


def _trajectory(
    episode_id: str,
    *,
    step_count: int = 1,
    status: str = "stopped",
    terminal_reward: float = 0.0,
) -> TrajectoryEpisode:
    observation = EnvObservation(
        episode_id,
        (),
        None,
        "local",
        {"parent_session_ids": []},
        None,
    )
    start = TrajectoryEpisodeStart(episode_id, observation)
    steps = tuple(
        TrajectoryStep(
            episode_id=episode_id,
            step_index=index,
            action=ToolAction("tool", {"index": index}),
            transcript_delta=(),
            tool_result={"value": index},
            reward=1.0,
            terminated=False,
            truncated=False,
        )
        for index in range(step_count)
    )
    end = TrajectoryEpisodeEnd(
        episode_id=episode_id,
        step_count=step_count,
        transition_reward=float(step_count),
        terminal_reward=terminal_reward,
        total_reward=float(step_count) + terminal_reward,
        terminated=False,
        truncated=False,
        status=status,
        final_observation=observation,
    )
    return TrajectoryEpisode(start, steps, end)


def _rollout(
    episode_id: str,
    *,
    step_count: int = 1,
    terminal_reward: float = 0.0,
) -> EpisodeRollout:
    trajectory = _trajectory(
        episode_id, step_count=step_count, terminal_reward=terminal_reward
    )
    summary = RolloutEpisode(
        episode_id=episode_id,
        task_id=None,
        reward=float(step_count) + terminal_reward,
        terminated=False,
        truncated=False,
        steps=step_count,
        status="stopped",
    )
    return EpisodeRollout(summary, trajectory)


def test_episode_rollout_rejects_summary_mismatches() -> None:
    rollout = _rollout("one")
    with pytest.raises(TrainingBatchError, match="IDs"):
        EpisodeRollout(replace(rollout.episode, episode_id="other"), rollout.trajectory)
    with pytest.raises(TrainingBatchError, match="step count"):
        EpisodeRollout(replace(rollout.episode, steps=2), rollout.trajectory)
    with pytest.raises(TrainingBatchError, match="reward"):
        EpisodeRollout(replace(rollout.episode, reward=99.0), rollout.trajectory)
    with pytest.raises(TrainingBatchError, match="status"):
        EpisodeRollout(replace(rollout.episode, status="failed"), rollout.trajectory)


def test_completed_rollout_requires_episode_end() -> None:
    trajectory = _trajectory("one")
    incomplete = TrajectoryEpisode(trajectory.start, trajectory.steps, None)
    summary = replace(_rollout("one").episode, status="completed")
    with pytest.raises(TrainingBatchError, match="episode_end"):
        EpisodeRollout(summary, incomplete)


def test_zero_step_terminal_reward_is_valid() -> None:
    rollout = _rollout("zero", step_count=0, terminal_reward=2.5)
    assert rollout.episode.reward == 2.5
    assert rollout.trajectory.end.terminal_reward == 2.5  # type: ignore[union-attr]


def test_batch_rejects_duplicate_episode_ids() -> None:
    with pytest.raises(TrainingBatchError, match="duplicate"):
        RolloutBatch((_rollout("one"), _rollout("one")))


def test_select_preserves_order_and_ownership() -> None:
    batch = RolloutBatch((_rollout("a", step_count=1), _rollout("b", step_count=2)))
    selected = batch.select([1, 0])
    assert [episode.episode_id for episode in selected.episodes] == ["b", "a"]
    assert [step.episode_id for step in selected.rollouts[0].trajectory.steps] == [
        "b",
        "b",
    ]
    with pytest.raises(TrainingBatchError, match="unique"):
        batch.select([0, 0])
    with pytest.raises(IndexError):
        batch.select([-1])
    with pytest.raises(IndexError):
        batch.select([2])


def test_concat_retains_source_metadata_and_rejects_duplicates() -> None:
    left = RolloutBatch((_rollout("a"),), {"source": "left"})
    right = RolloutBatch((_rollout("b"),), {"source": "right"})
    combined = RolloutBatch.concat((left, right))
    assert combined.meta_info["sources"] == [
        {"source": "left"},
        {"source": "right"},
    ]
    assert RolloutBatch.concat(()).num_episodes == 0
    with pytest.raises(TrainingBatchError, match="duplicate"):
        RolloutBatch.concat((left, left))


def test_iterator_shuffle_is_deterministic_and_batches_remain_valid() -> None:
    batch = RolloutBatch(tuple(_rollout(str(index)) for index in range(6)))
    first = [
        [episode.episode_id for episode in mini.episodes]
        for mini in batch.make_iterator(2, epochs=2, seed=7)
    ]
    second = [
        [episode.episode_id for episode in mini.episodes]
        for mini in batch.make_iterator(2, epochs=2, seed=7)
    ]
    assert first == second
    assert all(len(group) <= 2 for group in first)
    assert batch.num_steps == 6


def test_wire_payload_is_episode_aligned() -> None:
    batch = RolloutBatch((_rollout("a"), _rollout("b", step_count=2)))
    payload = batch.to_wire_payload()["non_tensor_batch"]
    assert payload["episode_ids"] == ["a", "b"]
    assert len(payload["trajectory_records"]) == 2
    assert len(payload["trajectory_records"][1]) == 4
