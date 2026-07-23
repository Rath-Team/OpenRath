"""Validated episode-owned rollout batches."""

from __future__ import annotations

import math
import random
from collections.abc import Iterator, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from rath.env import TrajectoryEpisode, TrajectoryStep, write_trajectory_jsonl
from rath.env.observations import jsonable_value
from rath.training.errors import TrainingBatchError

__all__ = [
    "ROLLOUT_BATCH_SCHEMA_VERSION",
    "EpisodeRollout",
    "RolloutBatch",
    "RolloutEpisode",
]

ROLLOUT_BATCH_SCHEMA_VERSION = 1


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=1e-9)


@dataclass(frozen=True, slots=True)
class RolloutEpisode:
    episode_id: str
    task_id: str | None
    reward: float
    terminated: bool
    truncated: bool
    steps: int
    status: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.episode_id, str) or not self.episode_id.strip():
            raise TrainingBatchError("episode_id must be a non-empty string")
        if self.task_id is not None and (
            not isinstance(self.task_id, str) or not self.task_id.strip()
        ):
            raise TrainingBatchError("task_id must be None or a non-empty string")
        reward = float(self.reward)
        if not math.isfinite(reward):
            raise TrainingBatchError("episode reward must be finite")
        if not isinstance(self.terminated, bool) or not isinstance(
            self.truncated, bool
        ):
            raise TrainingBatchError("terminal flags must be booleans")
        if self.terminated and self.truncated:
            raise TrainingBatchError("rollout cannot be terminated and truncated")
        if type(self.steps) is not int or self.steps < 0:
            raise TrainingBatchError("steps must be a non-negative integer")
        if not isinstance(self.status, str) or not self.status:
            raise TrainingBatchError("status must be a non-empty string")
        if not isinstance(self.metadata, Mapping):
            raise TrainingBatchError("metadata must be a mapping")
        if self.error is not None and not isinstance(self.error, str):
            raise TrainingBatchError("error must be None or a string")
        metadata = jsonable_value(deepcopy(dict(self.metadata)), path="metadata")
        assert isinstance(metadata, dict)
        object.__setattr__(self, "reward", reward)
        object.__setattr__(self, "metadata", MappingProxyType(metadata))

    @property
    def done(self) -> bool:
        return self.terminated or self.truncated

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "schema_version": ROLLOUT_BATCH_SCHEMA_VERSION,
            "record_type": "openrath_rollout_episode",
            "episode_id": self.episode_id,
            "task_id": self.task_id,
            "reward": self.reward,
            "terminated": self.terminated,
            "truncated": self.truncated,
            "done": self.done,
            "steps": self.steps,
            "status": self.status,
            "metadata": jsonable_value(self.metadata, path="metadata"),
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class EpisodeRollout:
    episode: RolloutEpisode
    trajectory: TrajectoryEpisode

    def __post_init__(self) -> None:
        summary = self.episode
        trajectory = self.trajectory
        if summary.episode_id != trajectory.episode_id:
            raise TrainingBatchError("episode summary and trajectory IDs do not match")
        if summary.steps != len(trajectory.steps):
            raise TrainingBatchError("episode step count does not match trajectory")
        end = trajectory.end
        if end is None:
            if summary.status in {"completed", "stopped", "max_steps"}:
                raise TrainingBatchError(
                    f"{summary.status} rollout requires an episode_end record"
                )
            expected_reward = float(sum(step.reward for step in trajectory.steps))
            if not _close(summary.reward, expected_reward):
                raise TrainingBatchError("incomplete rollout reward mismatch")
            return
        if not _close(summary.reward, end.total_reward):
            raise TrainingBatchError("episode reward does not match trajectory total")
        if (summary.terminated, summary.truncated) != (
            end.terminated,
            end.truncated,
        ):
            raise TrainingBatchError("episode terminal flags do not match trajectory")
        if summary.status != end.status:
            raise TrainingBatchError("episode status does not match trajectory end")


@dataclass(frozen=True, slots=True)
class RolloutBatch:
    rollouts: tuple[EpisodeRollout, ...] = ()
    meta_info: Mapping[str, Any] = field(default_factory=dict)
    _step_slices: tuple[tuple[int, int], ...] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        rollouts = tuple(self.rollouts)
        ids = [rollout.episode.episode_id for rollout in rollouts]
        if len(ids) != len(set(ids)):
            raise TrainingBatchError("RolloutBatch contains duplicate episode IDs")
        if not isinstance(self.meta_info, Mapping):
            raise TrainingBatchError("meta_info must be a mapping")
        meta = jsonable_value(deepcopy(dict(self.meta_info)), path="meta_info")
        assert isinstance(meta, dict)
        slices: list[tuple[int, int]] = []
        cursor = 0
        for rollout in rollouts:
            next_cursor = cursor + len(rollout.trajectory.steps)
            slices.append((cursor, next_cursor))
            cursor = next_cursor
        object.__setattr__(self, "rollouts", rollouts)
        object.__setattr__(self, "meta_info", MappingProxyType(meta))
        object.__setattr__(self, "_step_slices", tuple(slices))

    @property
    def episodes(self) -> tuple[RolloutEpisode, ...]:
        return tuple(rollout.episode for rollout in self.rollouts)

    @property
    def trajectories(self) -> tuple[TrajectoryStep, ...]:
        return tuple(
            step for rollout in self.rollouts for step in rollout.trajectory.steps
        )

    @property
    def num_episodes(self) -> int:
        return len(self.rollouts)

    @property
    def num_steps(self) -> int:
        return 0 if not self._step_slices else self._step_slices[-1][1]

    @property
    def total_reward(self) -> float:
        return float(sum(episode.reward for episode in self.episodes))

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "schema_version": ROLLOUT_BATCH_SCHEMA_VERSION,
            "record_type": "openrath_rollout_batch",
            "rollouts": [
                {
                    "episode": rollout.episode.to_jsonable(),
                    "trajectory": {
                        "start": rollout.trajectory.start.to_jsonable(),
                        "steps": [
                            step.to_jsonable() for step in rollout.trajectory.steps
                        ],
                        "end": (
                            None
                            if rollout.trajectory.end is None
                            else rollout.trajectory.end.to_jsonable()
                        ),
                    },
                }
                for rollout in self.rollouts
            ],
            "meta_info": jsonable_value(self.meta_info, path="meta_info"),
        }

    def to_wire_payload(self) -> dict[str, Any]:
        """Return an episode-aligned, framework-neutral trainer payload."""

        trajectory_records = [
            [record.to_jsonable() for record in rollout.trajectory.records()]
            for rollout in self.rollouts
        ]
        return {
            "schema_version": ROLLOUT_BATCH_SCHEMA_VERSION,
            "record_type": "openrath_rollout_wire",
            "non_tensor_batch": {
                "episode_ids": [episode.episode_id for episode in self.episodes],
                "task_ids": [episode.task_id for episode in self.episodes],
                "rewards": [episode.reward for episode in self.episodes],
                "terminated": [episode.terminated for episode in self.episodes],
                "truncated": [episode.truncated for episode in self.episodes],
                "dones": [episode.done for episode in self.episodes],
                "statuses": [episode.status for episode in self.episodes],
                "errors": [episode.error for episode in self.episodes],
                "episodes": [episode.to_jsonable() for episode in self.episodes],
                "trajectory_records": trajectory_records,
            },
            "meta_info": jsonable_value(self.meta_info, path="meta_info"),
        }

    def trajectory_jsonl(self) -> str:
        from rath.env import trajectory_to_jsonl

        return trajectory_to_jsonl(
            tuple(rollout.trajectory for rollout in self.rollouts)
        )

    def write_trajectory_jsonl(self, path: str | Path) -> None:
        write_trajectory_jsonl(
            tuple(rollout.trajectory for rollout in self.rollouts), path
        )

    def select(self, indices: Sequence[int]) -> "RolloutBatch":
        normalized = list(indices)
        if len(normalized) != len(set(normalized)):
            raise TrainingBatchError("select indices must be unique")
        for index in normalized:
            if index < 0 or index >= len(self.rollouts):
                raise IndexError(f"rollout index out of range: {index}")
        return RolloutBatch(
            tuple(self.rollouts[index] for index in normalized),
            meta_info=self.meta_info,
        )

    @staticmethod
    def concat(batches: Sequence["RolloutBatch"]) -> "RolloutBatch":
        if not batches:
            return RolloutBatch()
        rollouts = tuple(rollout for batch in batches for rollout in batch.rollouts)
        return RolloutBatch(
            rollouts,
            meta_info={
                "sources": [dict(batch.meta_info) for batch in batches],
                "num_batches": len(batches),
            },
        )

    def make_iterator(
        self,
        mini_batch_size: int,
        *,
        epochs: int = 1,
        seed: int | None = None,
    ) -> Iterator["RolloutBatch"]:
        if mini_batch_size <= 0:
            raise ValueError("mini_batch_size must be positive")
        if epochs <= 0:
            raise ValueError("epochs must be positive")
        rng = random.Random(seed)
        base = list(range(self.num_episodes))
        for _ in range(epochs):
            indices = list(base)
            if seed is not None:
                rng.shuffle(indices)
            for start in range(0, len(indices), mini_batch_size):
                yield self.select(indices[start : start + mini_batch_size])
