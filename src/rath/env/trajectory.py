"""Compact, versioned episode trajectory records and strict JSONL codec."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any

from rath.env.actions import ToolAction
from rath.env.observations import (
    EnvObservation,
    jsonable_value,
    latest_tool_result_from_chunks,
)
from rath.persistence import dumps_jsonl, iter_jsonl, write_jsonl

__all__ = [
    "TRAJECTORY_SCHEMA_VERSION",
    "utc_now_iso",
    "MaterializedTrajectoryStep",
    "TrajectoryEpisode",
    "TrajectoryEpisodeEnd",
    "TrajectoryEpisodeStart",
    "TrajectoryStep",
    "load_trajectory_jsonl",
    "materialize_trajectory",
    "trajectory_to_jsonl",
    "write_trajectory_jsonl",
]

TRAJECTORY_SCHEMA_VERSION = 2


def utc_now_iso() -> str:
    """ISO-8601 UTC stamp. ATIF requires a timestamp on every step."""

    return datetime.now(timezone.utc).isoformat()


def _non_empty(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _finite(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _mapping(value: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    projected = jsonable_value(deepcopy(dict(value)), path=name)
    assert isinstance(projected, dict)
    return MappingProxyType(projected)


@dataclass(frozen=True, slots=True)
class TrajectoryEpisodeStart:
    episode_id: str
    initial_observation: EnvObservation
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        _non_empty(self.episode_id, "episode_id")
        _non_empty(self.created_at, "created_at")
        if self.initial_observation.session_id != self.episode_id:
            raise ValueError("episode_start observation session_id mismatch")
        object.__setattr__(self, "metadata", _mapping(self.metadata, "metadata"))

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "schema_version": TRAJECTORY_SCHEMA_VERSION,
            "record_type": "episode_start",
            "episode_id": self.episode_id,
            "initial_observation": self.initial_observation.to_jsonable(),
            "metadata": jsonable_value(self.metadata, path="metadata"),
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class TrajectoryStep:
    episode_id: str
    step_index: int
    action: ToolAction
    transcript_delta: tuple[dict[str, Any], ...]
    tool_result: Mapping[str, Any] | None
    reward: float
    terminated: bool
    truncated: bool
    info: Mapping[str, Any] = field(default_factory=dict)
    status: str = "completed"
    error: Mapping[str, Any] | None = None
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        _non_empty(self.episode_id, "episode_id")
        _non_empty(self.created_at, "created_at")
        if type(self.step_index) is not int or self.step_index < 0:
            raise ValueError("step_index must be a non-negative integer")
        if not isinstance(self.terminated, bool) or not isinstance(
            self.truncated, bool
        ):
            raise TypeError("trajectory terminal flags must be booleans")
        if self.terminated and self.truncated:
            raise ValueError("a trajectory step cannot be terminated and truncated")
        object.__setattr__(self, "reward", _finite(self.reward, "reward"))
        delta = jsonable_value(self.transcript_delta, path="transcript_delta")
        assert isinstance(delta, list)
        object.__setattr__(self, "transcript_delta", tuple(dict(row) for row in delta))
        if self.tool_result is not None:
            object.__setattr__(
                self, "tool_result", _mapping(self.tool_result, "tool_result")
            )
        object.__setattr__(self, "info", _mapping(self.info, "info"))
        _non_empty(self.status, "status")
        if self.error is not None:
            object.__setattr__(self, "error", _mapping(self.error, "error"))
        if (self.status == "failed" or self.status.endswith("_failed")) and (
            self.error is None
        ):
            raise ValueError("failed trajectory steps require error details")

    @property
    def done(self) -> bool:
        return self.terminated or self.truncated

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "schema_version": TRAJECTORY_SCHEMA_VERSION,
            "record_type": "step",
            "episode_id": self.episode_id,
            "step_index": self.step_index,
            "action": self.action.to_jsonable(),
            "transcript_delta": jsonable_value(
                self.transcript_delta, path="transcript_delta"
            ),
            "tool_result": jsonable_value(self.tool_result, path="tool_result"),
            "reward": self.reward,
            "terminated": self.terminated,
            "truncated": self.truncated,
            "info": jsonable_value(self.info, path="info"),
            "status": self.status,
            "error": jsonable_value(self.error, path="error"),
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class TrajectoryEpisodeEnd:
    episode_id: str
    step_count: int
    transition_reward: float
    terminal_reward: float
    total_reward: float
    terminated: bool
    truncated: bool
    status: str
    final_observation: EnvObservation | None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    error: Mapping[str, Any] | None = None
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        _non_empty(self.episode_id, "episode_id")
        _non_empty(self.created_at, "created_at")
        if type(self.step_count) is not int or self.step_count < 0:
            raise ValueError("step_count must be a non-negative integer")
        if not isinstance(self.terminated, bool) or not isinstance(
            self.truncated, bool
        ):
            raise TypeError("episode terminal flags must be booleans")
        if self.terminated and self.truncated:
            raise ValueError("an episode cannot be terminated and truncated")
        object.__setattr__(
            self,
            "transition_reward",
            _finite(self.transition_reward, "transition_reward"),
        )
        object.__setattr__(
            self, "terminal_reward", _finite(self.terminal_reward, "terminal_reward")
        )
        object.__setattr__(
            self, "total_reward", _finite(self.total_reward, "total_reward")
        )
        _non_empty(self.status, "status")
        if self.final_observation is not None:
            if self.final_observation.session_id != self.episode_id:
                raise ValueError("episode_end observation session_id mismatch")
        object.__setattr__(self, "metadata", _mapping(self.metadata, "metadata"))
        if self.error is not None:
            object.__setattr__(self, "error", _mapping(self.error, "error"))

    @property
    def done(self) -> bool:
        return self.terminated or self.truncated

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "schema_version": TRAJECTORY_SCHEMA_VERSION,
            "record_type": "episode_end",
            "episode_id": self.episode_id,
            "step_count": self.step_count,
            "transition_reward": self.transition_reward,
            "terminal_reward": self.terminal_reward,
            "total_reward": self.total_reward,
            "terminated": self.terminated,
            "truncated": self.truncated,
            "status": self.status,
            "final_observation": (
                None
                if self.final_observation is None
                else self.final_observation.to_jsonable()
            ),
            "metadata": jsonable_value(self.metadata, path="metadata"),
            "error": jsonable_value(self.error, path="error"),
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class TrajectoryEpisode:
    start: TrajectoryEpisodeStart
    steps: tuple[TrajectoryStep, ...] = ()
    end: TrajectoryEpisodeEnd | None = None

    def __post_init__(self) -> None:
        episode_id = self.start.episode_id
        done_seen = False
        for expected, step in enumerate(self.steps):
            if step.episode_id != episode_id:
                raise ValueError("trajectory contains mixed episode IDs")
            if step.step_index != expected:
                raise ValueError("trajectory step indices must be contiguous from zero")
            if done_seen:
                raise ValueError("trajectory contains steps after a terminal step")
            done_seen = step.done
        end = self.end
        if end is None:
            return
        if end.episode_id != episode_id:
            raise ValueError("episode_end ID does not match episode_start")
        if end.step_count != len(self.steps):
            raise ValueError("episode_end step_count does not match trajectory")
        transition_reward = float(sum(step.reward for step in self.steps))
        if not math.isclose(
            end.transition_reward, transition_reward, rel_tol=0.0, abs_tol=1e-9
        ):
            raise ValueError(
                "episode_end transition_reward does not equal step rewards"
            )
        if not math.isclose(
            end.total_reward,
            end.transition_reward + end.terminal_reward,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("episode_end total_reward is inconsistent")
        if self.steps and self.steps[-1].done:
            last = self.steps[-1]
            if (last.terminated, last.truncated) != (end.terminated, end.truncated):
                raise ValueError("episode_end flags do not match terminal step")
        if end.status == "completed" and not end.terminated:
            raise ValueError("completed episode must be terminated")
        if end.status == "max_steps" and not end.truncated:
            raise ValueError("max_steps episode must be truncated")
        if end.status == "stopped" and end.done:
            raise ValueError("stopped episode cannot be terminated or truncated")
        if end.status == "completed" and end.final_observation is None:
            raise ValueError("completed episode requires a final observation")
        if (
            end.status == "failed" or end.status.endswith("_failed")
        ) and end.error is None:
            raise ValueError("failed episode status requires error details")

    @property
    def episode_id(self) -> str:
        return self.start.episode_id

    def records(self) -> tuple[Any, ...]:
        suffix: tuple[Any, ...] = () if self.end is None else (self.end,)
        return (self.start, *self.steps, *suffix)


@dataclass(frozen=True, slots=True)
class MaterializedTrajectoryStep:
    observation: EnvObservation
    step: TrajectoryStep
    next_observation: EnvObservation


def _record_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, TrajectoryEpisode):
        return [record.to_jsonable() for record in value.records()]
    if isinstance(
        value, (TrajectoryEpisodeStart, TrajectoryStep, TrajectoryEpisodeEnd)
    ):
        return [value.to_jsonable()]
    rows: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, TrajectoryEpisode):
            rows.extend(record.to_jsonable() for record in item.records())
        else:
            rows.append(item.to_jsonable())
    return rows


def trajectory_to_jsonl(value: Any) -> str:
    return dumps_jsonl(_record_rows(value))


def write_trajectory_jsonl(
    value: Any,
    path: str | Path,
    *,
    append: bool = False,
) -> None:
    write_jsonl(path, _record_rows(value), append=append)


def _require_mapping(raw: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise TypeError(f"{name} must be an object")
    return raw


def _require_string(raw: Any, name: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return raw


def _require_bool(raw: Any, name: str) -> bool:
    if not isinstance(raw, bool):
        raise TypeError(f"{name} must be a boolean")
    return raw


def _require_int(raw: Any, name: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError(f"{name} must be an integer")
    return raw


def _require_number(raw: Any, name: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise TypeError(f"{name} must be a number")
    return float(raw)


def _decode_record(raw: Mapping[str, Any]) -> Any:
    record_type = raw["record_type"]
    if record_type == "episode_start":
        return TrajectoryEpisodeStart(
            episode_id=_require_string(raw["episode_id"], "episode_id"),
            initial_observation=EnvObservation.from_mapping(
                _require_mapping(raw["initial_observation"], "initial_observation")
            ),
            metadata=_require_mapping(raw.get("metadata", {}), "metadata"),
            created_at=_require_string(raw["created_at"], "created_at"),
        )
    if record_type == "step":
        tool_result = raw.get("tool_result")
        error = raw.get("error")
        delta = raw.get("transcript_delta", ())
        if not isinstance(delta, Sequence) or isinstance(delta, (str, bytes)):
            raise TypeError("transcript_delta must be a sequence")
        return TrajectoryStep(
            episode_id=_require_string(raw["episode_id"], "episode_id"),
            step_index=_require_int(raw["step_index"], "step_index"),
            action=ToolAction.from_mapping(_require_mapping(raw["action"], "action")),
            transcript_delta=tuple(
                dict(_require_mapping(row, "transcript_delta row")) for row in delta
            ),
            tool_result=(
                None
                if tool_result is None
                else _require_mapping(tool_result, "tool_result")
            ),
            reward=_require_number(raw["reward"], "reward"),
            terminated=_require_bool(raw["terminated"], "terminated"),
            truncated=_require_bool(raw["truncated"], "truncated"),
            info=_require_mapping(raw.get("info", {}), "info"),
            status=_require_string(raw.get("status", "completed"), "status"),
            error=None if error is None else _require_mapping(error, "error"),
            created_at=_require_string(raw["created_at"], "created_at"),
        )
    if record_type == "episode_end":
        final = raw.get("final_observation")
        error = raw.get("error")
        return TrajectoryEpisodeEnd(
            episode_id=_require_string(raw["episode_id"], "episode_id"),
            step_count=_require_int(raw["step_count"], "step_count"),
            transition_reward=_require_number(
                raw["transition_reward"], "transition_reward"
            ),
            terminal_reward=_require_number(raw["terminal_reward"], "terminal_reward"),
            total_reward=_require_number(raw["total_reward"], "total_reward"),
            terminated=_require_bool(raw["terminated"], "terminated"),
            truncated=_require_bool(raw["truncated"], "truncated"),
            status=_require_string(raw["status"], "status"),
            final_observation=(
                None
                if final is None
                else EnvObservation.from_mapping(
                    _require_mapping(final, "final_observation")
                )
            ),
            metadata=_require_mapping(raw.get("metadata", {}), "metadata"),
            error=None if error is None else _require_mapping(error, "error"),
            created_at=_require_string(raw["created_at"], "created_at"),
        )
    raise ValueError(f"unknown trajectory record_type {record_type!r}")


def load_trajectory_jsonl(path: str | Path) -> tuple[TrajectoryEpisode, ...]:
    target = Path(path)
    episodes: list[TrajectoryEpisode] = []
    start: TrajectoryEpisodeStart | None = None
    steps: list[TrajectoryStep] = []
    for line_number, raw in iter_jsonl(target):
        try:
            version = raw.get("schema_version")
            if type(version) is not int or version != TRAJECTORY_SCHEMA_VERSION:
                if type(version) is int and version > TRAJECTORY_SCHEMA_VERSION:
                    raise ValueError(f"unsupported future schema_version {version}")
                raise ValueError(f"unsupported schema_version {version!r}")
            record = _decode_record(raw)
            if isinstance(record, TrajectoryEpisodeStart):
                if start is not None:
                    raise ValueError("nested episode_start before episode_end")
                start = record
                steps = []
            elif isinstance(record, TrajectoryStep):
                if start is None:
                    raise ValueError("trajectory step appears before episode_start")
                steps.append(record)
            else:
                if start is None:
                    raise ValueError("episode_end appears before episode_start")
                episodes.append(TrajectoryEpisode(start, tuple(steps), record))
                start = None
                steps = []
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{target}:{line_number}: {exc}") from exc
    if start is not None:
        try:
            episodes.append(TrajectoryEpisode(start, tuple(steps), None))
        except ValueError as exc:
            raise ValueError(f"{target}: EOF: {exc}") from exc
    return tuple(episodes)


def materialize_trajectory(
    episode: TrajectoryEpisode,
) -> tuple[MaterializedTrajectoryStep, ...]:
    current = episode.start.initial_observation
    materialized: list[MaterializedTrajectoryStep] = []
    for step in episode.steps:
        chunks = current.chunks + step.transcript_delta
        next_observation = replace(
            current,
            chunks=chunks,
            latest_tool_result=latest_tool_result_from_chunks(chunks),
        )
        materialized.append(MaterializedTrajectoryStep(current, step, next_observation))
        current = next_observation
    if episode.end is not None and episode.end.final_observation is not None:
        if current != episode.end.final_observation:
            raise ValueError("materialized trajectory does not match final_observation")
    return tuple(materialized)
