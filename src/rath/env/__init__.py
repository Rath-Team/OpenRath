"""Environment-style execution and compact trajectory APIs."""

from rath.env.actions import ToolAction
from rath.env.core import OpenRathEnv, OpenRathEnvConfig, StepResult
from rath.env.errors import (
    EnvSetupError,
    EnvStepError,
    TrajectoryPersistenceError,
)
from rath.env.observations import EnvObservation, observation_from_session
from rath.env.rewards import RewardFn, RewardResult
from rath.env.trajectory import (
    TRAJECTORY_SCHEMA_VERSION,
    MaterializedTrajectoryStep,
    TrajectoryEpisode,
    TrajectoryEpisodeEnd,
    TrajectoryEpisodeStart,
    TrajectoryStep,
    load_trajectory_jsonl,
    materialize_trajectory,
    trajectory_to_jsonl,
    utc_now_iso,
    write_trajectory_jsonl,
)

__all__ = [
    "TRAJECTORY_SCHEMA_VERSION",
    "EnvObservation",
    "EnvSetupError",
    "EnvStepError",
    "MaterializedTrajectoryStep",
    "OpenRathEnv",
    "OpenRathEnvConfig",
    "RewardFn",
    "RewardResult",
    "StepResult",
    "ToolAction",
    "TrajectoryEpisode",
    "TrajectoryEpisodeEnd",
    "TrajectoryEpisodeStart",
    "TrajectoryPersistenceError",
    "TrajectoryStep",
    "load_trajectory_jsonl",
    "materialize_trajectory",
    "observation_from_session",
    "trajectory_to_jsonl",
    "utc_now_iso",
    "write_trajectory_jsonl",
]
