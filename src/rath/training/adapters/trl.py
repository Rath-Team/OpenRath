"""Lazy adapter from :class:`RolloutBatch` to a TRL-consumable ``datasets.Dataset``.

OpenRath owns no trainer tensors. Each row is one episode: the task prompt, the
assistant's tool-call transcript as a completion, the scalar reward TRL's GRPO and
PPO trainers consume, and the full ATIF document for anything that wants the
trajectory rather than the summary.
"""

from __future__ import annotations

import importlib
import json
from typing import Any

from rath.env import to_atif
from rath.training.batch import EpisodeRollout, RolloutBatch
from rath.training.errors import TrainingAdapterError

__all__ = ["to_trl_dataset"]

_INSTALL = "pip install 'openrath[trl]'"


def _load_datasets() -> Any:
    try:
        return importlib.import_module("datasets")
    except (ImportError, ModuleNotFoundError) as exc:
        raise TrainingAdapterError(
            f"TRL adapter dependencies are not installed; run {_INSTALL}"
        ) from exc


def _prompt(rollout: EpisodeRollout) -> str:
    """The task as the model first saw it: the initial user chunk."""

    for chunk in rollout.trajectory.start.initial_observation.chunks:
        if chunk.get("kind") == "user":
            payload = chunk.get("payload") or {}
            return str(payload.get("content") or "")
    return ""


def _completion(rollout: EpisodeRollout) -> str:
    """One JSON line per action taken, in order."""

    return "\n".join(
        json.dumps(step.action.to_jsonable(), ensure_ascii=False)
        for step in rollout.trajectory.steps
    )


def to_trl_dataset(batch: RolloutBatch) -> Any:
    """One row per episode: prompt, completion, reward, and the ATIF document."""

    if not isinstance(batch, RolloutBatch):
        raise TypeError("batch must be a RolloutBatch")
    datasets = _load_datasets()
    rows = [
        {
            "episode_id": rollout.episode.episode_id,
            "task_id": rollout.episode.task_id,
            "prompt": _prompt(rollout),
            "completion": _completion(rollout),
            "reward": rollout.episode.reward,
            "status": rollout.episode.status,
            "atif": to_atif(rollout.trajectory),
        }
        for rollout in batch.rollouts
    ]
    return datasets.Dataset.from_list(rows)
