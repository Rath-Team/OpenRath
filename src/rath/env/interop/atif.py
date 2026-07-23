"""Export a compact trajectory as ATIF (Agent Trajectory Interchange Format).

ATIF is Harbor's interchange format; TRL and SkyRL read it. A trajectory format
nobody else can read is a parallel universe, so this is the passport out of ours.

The version is pinned deliberately. ATIF added fields at 1.3, 1.4, 1.6, and 1.7; a
bump is a code change, never a silent reinterpretation of the same document.

Export only. ATIF import is not implemented because no consumer has asked for it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from rath.env.observations import jsonable_value
from rath.env.trajectory import TrajectoryEpisode, TrajectoryStep

__all__ = ["ATIF_SCHEMA_VERSION", "to_atif"]

ATIF_SCHEMA_VERSION = "ATIF-v1.7"


def _call_id(step: TrajectoryStep) -> str:
    return f"{step.episode_id}_step_{step.step_index}"


def _atif_step(step: TrajectoryStep) -> dict[str, Any]:
    call_id = _call_id(step)
    return {
        "step_id": step.step_index + 1,  # ATIF numbers steps from one
        "timestamp": step.created_at,
        "source": "agent",
        "message": None,
        "tool_calls": [
            {
                "tool_call_id": call_id,
                "function_name": step.action.tool_name,
                "arguments": jsonable_value(step.action.arguments, path="arguments"),
            }
        ],
        "observation": {
            "results": [
                {
                    "source_call_id": call_id,
                    "content": jsonable_value(step.tool_result, path="tool_result"),
                }
            ]
        },
        "metrics": {"reward": step.reward},
        # OpenRath-specific fields ride in `extra`, which is where ATIF puts them.
        "extra": {
            "status": step.status,
            "terminated": step.terminated,
            "truncated": step.truncated,
            "info": jsonable_value(step.info, path="info"),
            "error": jsonable_value(step.error, path="error"),
        },
    }


def to_atif(
    episode: TrajectoryEpisode,
    *,
    agent: Mapping[str, Any] | None = None,
    subagents: Sequence[TrajectoryEpisode] = (),
) -> dict[str, Any]:
    """Project one episode into an ATIF-v1.7 document."""

    end = episode.end
    final_metrics: dict[str, Any] = {
        "status": "incomplete" if end is None else end.status,
        "step_count": len(episode.steps),
        "total_reward": 0.0 if end is None else end.total_reward,
        "transition_reward": (
            float(sum(step.reward for step in episode.steps))
            if end is None
            else end.transition_reward
        ),
        "terminal_reward": 0.0 if end is None else end.terminal_reward,
        "terminated": False if end is None else end.terminated,
        "truncated": False if end is None else end.truncated,
    }
    return {
        "schema_version": ATIF_SCHEMA_VERSION,
        "session_id": episode.episode_id,
        "trajectory_id": episode.episode_id,
        "agent": dict(agent or {"name": "openrath"}),
        "steps": [_atif_step(step) for step in episode.steps],
        "final_metrics": final_metrics,
        "subagent_trajectories": [to_atif(child) for child in subagents],
        "extra": {
            "openrath_trajectory_schema_version": episode.start.to_jsonable()[
                "schema_version"
            ],
            "created_at": episode.start.created_at,
        },
    }
