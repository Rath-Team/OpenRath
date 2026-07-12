"""Lazy adapter from :class:`RolloutBatch` to a real verl ``DataProto``."""

from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from typing import Any

from rath.env.observations import jsonable_value
from rath.training.batch import ROLLOUT_BATCH_SCHEMA_VERSION, RolloutBatch
from rath.training.errors import TrainingAdapterError

__all__ = ["to_verl_data_proto"]

_INSTALL = "pip install 'openrath[verl]'"
_CANONICAL_META_KEYS = {
    "openrath_schema_version",
    "openrath_num_episodes",
    "openrath_num_steps",
}


def _object_array(np: Any, values: Sequence[Any]) -> Any:
    array = np.empty(len(values), dtype=object)
    array[:] = list(values)
    return array


def _load_verl_api() -> tuple[Any, Any, str]:
    try:
        np = importlib.import_module("numpy")
        verl = importlib.import_module("verl")
        protocol = importlib.import_module("verl.protocol")
    except (ImportError, ModuleNotFoundError) as exc:
        raise TrainingAdapterError(
            f"verl adapter dependencies are not installed; run {_INSTALL}"
        ) from exc
    version = str(getattr(verl, "__version__", "unknown"))
    data_proto = getattr(protocol, "DataProto", None)
    if data_proto is None:
        raise TrainingAdapterError(
            f"incompatible verl {version}: verl.protocol.DataProto is missing"
        )
    from_dict = getattr(data_proto, "from_dict", None)
    if not callable(from_dict):
        raise TrainingAdapterError(
            f"incompatible verl {version}: DataProto.from_dict is missing or not callable"
        )
    return np, data_proto, version


def to_verl_data_proto(
    batch: RolloutBatch,
    *,
    tensors: Mapping[str, Any] | None = None,
    non_tensors: Mapping[str, Sequence[Any]] | None = None,
    meta_info: Mapping[str, Any] | None = None,
) -> Any:
    """Convert an episode-owned batch to ``verl.protocol.DataProto``.

    OpenRath owns no trainer tensors. Callers may provide already-tokenized
    tensors; the adapter adds batch-aligned NumPy object arrays containing the
    canonical episode summaries and compact trajectory records.
    """

    if not isinstance(batch, RolloutBatch):
        raise TypeError("batch must be a RolloutBatch")
    np, data_proto, version = _load_verl_api()

    episodes = batch.episodes
    trajectories = tuple(rollout.trajectory for rollout in batch.rollouts)
    canonical: dict[str, Any] = {
        "episode_ids": _object_array(np, [episode.episode_id for episode in episodes]),
        "task_ids": _object_array(np, [episode.task_id for episode in episodes]),
        "rewards": _object_array(np, [episode.reward for episode in episodes]),
        "terminated": _object_array(np, [episode.terminated for episode in episodes]),
        "truncated": _object_array(np, [episode.truncated for episode in episodes]),
        "dones": _object_array(np, [episode.done for episode in episodes]),
        "statuses": _object_array(np, [episode.status for episode in episodes]),
        "errors": _object_array(np, [episode.error for episode in episodes]),
        "actions": _object_array(
            np,
            [
                [step.action.to_jsonable() for step in trajectory.steps]
                for trajectory in trajectories
            ],
        ),
        "tool_results": _object_array(
            np,
            [
                # Project rather than hand over the stored mapping: TrajectoryStep
                # keeps it as a MappingProxyType, which no pickle-based transport
                # (Ray, DataProto.save_to_disk) can serialize.
                [
                    jsonable_value(step.tool_result, path="tool_result")
                    for step in trajectory.steps
                ]
                for trajectory in trajectories
            ],
        ),
        "trajectory_records": _object_array(
            np,
            [
                [record.to_jsonable() for record in trajectory.records()]
                for trajectory in trajectories
            ],
        ),
    }

    merged_non_tensors = dict(canonical)
    for key, values in dict(non_tensors or {}).items():
        if key in merged_non_tensors:
            raise TrainingAdapterError(
                f"non_tensors key {key!r} would overwrite a canonical OpenRath field"
            )
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
            raise TrainingAdapterError(
                f"non_tensors[{key!r}] must be a batch-aligned sequence"
            )
        if len(values) != batch.num_episodes:
            raise TrainingAdapterError(
                f"non_tensors[{key!r}] length {len(values)} does not match "
                f"batch size {batch.num_episodes}"
            )
        merged_non_tensors[key] = _object_array(np, values)

    merged_meta = dict(batch.meta_info)
    merged_meta.update(dict(meta_info or {}))
    collisions = _CANONICAL_META_KEYS.intersection(merged_meta)
    if collisions:
        joined = ", ".join(sorted(collisions))
        raise TrainingAdapterError(
            f"meta_info would overwrite canonical OpenRath keys: {joined}"
        )
    merged_meta.update(
        {
            "openrath_schema_version": ROLLOUT_BATCH_SCHEMA_VERSION,
            "openrath_num_episodes": batch.num_episodes,
            "openrath_num_steps": batch.num_steps,
        }
    )

    try:
        return data_proto.from_dict(
            tensors=dict(tensors or {}),
            non_tensors=merged_non_tensors,
            meta_info=merged_meta,
        )
    except (AttributeError, TypeError) as exc:
        raise TrainingAdapterError(
            f"incompatible verl {version}: DataProto.from_dict rejected the "
            "supported tensors/non_tensors/meta_info API"
        ) from exc
