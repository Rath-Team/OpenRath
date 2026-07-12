"""Trainer-facing validated rollout batches and bounded collectors."""

from rath.training.adapters import to_verl_data_proto
from rath.training.batch import (
    ROLLOUT_BATCH_SCHEMA_VERSION,
    EpisodeRollout,
    RolloutBatch,
    RolloutEpisode,
)
from rath.training.collectors import (
    EnvPolicyFn,
    collect_benchmark_rollouts,
    collect_env_rollouts,
)
from rath.training.errors import (
    TrainingAdapterError,
    TrainingBatchError,
    TrainingCollectionError,
)

__all__ = [
    "ROLLOUT_BATCH_SCHEMA_VERSION",
    "EnvPolicyFn",
    "EpisodeRollout",
    "RolloutBatch",
    "RolloutEpisode",
    "TrainingAdapterError",
    "TrainingBatchError",
    "TrainingCollectionError",
    "collect_benchmark_rollouts",
    "collect_env_rollouts",
    "to_verl_data_proto",
]
