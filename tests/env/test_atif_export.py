from __future__ import annotations

from rath.env import (
    ATIF_SCHEMA_VERSION,
    EnvObservation,
    ToolAction,
    TrajectoryEpisode,
    TrajectoryEpisodeEnd,
    TrajectoryEpisodeStart,
    TrajectoryStep,
    to_atif,
)


def _episode(episode_id: str = "ep") -> TrajectoryEpisode:
    observation = EnvObservation(
        episode_id, (), None, "local", {"parent_session_ids": []}, None
    )
    step = TrajectoryStep(
        episode_id=episode_id,
        step_index=0,
        action=ToolAction("run_shell_command", {"cmd": "pytest"}),
        transcript_delta=(),
        tool_result={"exit_code": 0},
        reward=1.0,
        terminated=True,
        truncated=False,
    )
    return TrajectoryEpisode(
        TrajectoryEpisodeStart(episode_id, observation),
        (step,),
        TrajectoryEpisodeEnd(
            episode_id=episode_id,
            step_count=1,
            transition_reward=1.0,
            terminal_reward=0.0,
            total_reward=1.0,
            terminated=True,
            truncated=False,
            status="completed",
            final_observation=observation,
        ),
    )


def test_root_fields_match_atif_v17() -> None:
    doc = to_atif(_episode())
    assert doc["schema_version"] == ATIF_SCHEMA_VERSION == "ATIF-v1.7"
    assert doc["session_id"] == "ep"
    assert doc["trajectory_id"] == "ep"
    assert set(doc) >= {
        "schema_version",
        "session_id",
        "trajectory_id",
        "agent",
        "steps",
        "final_metrics",
    }


def test_step_ids_start_at_one() -> None:
    assert [step["step_id"] for step in to_atif(_episode())["steps"]] == [1]


def test_tool_call_and_observation_are_linked_by_call_id() -> None:
    step = to_atif(_episode())["steps"][0]
    assert step["source"] == "agent"
    call = step["tool_calls"][0]
    assert call["function_name"] == "run_shell_command"
    assert call["arguments"] == {"cmd": "pytest"}
    result = step["observation"]["results"][0]
    assert result["source_call_id"] == call["tool_call_id"]
    assert result["content"] == {"exit_code": 0}


def test_step_carries_the_trajectory_timestamp() -> None:
    episode = _episode()
    doc = to_atif(episode)
    assert doc["steps"][0]["timestamp"] == episode.steps[0].created_at


def test_reward_and_status_ride_in_final_metrics() -> None:
    metrics = to_atif(_episode())["final_metrics"]
    assert metrics["total_reward"] == 1.0
    assert metrics["status"] == "completed"
    assert metrics["step_count"] == 1


def test_subagent_episodes_nest() -> None:
    doc = to_atif(_episode("parent"), subagents=[_episode("child")])
    assert doc["subagent_trajectories"][0]["trajectory_id"] == "child"


def test_an_episode_without_an_end_still_exports() -> None:
    episode = _episode()
    open_episode = TrajectoryEpisode(episode.start, episode.steps, None)
    doc = to_atif(open_episode)
    assert doc["final_metrics"]["status"] == "incomplete"
    assert doc["final_metrics"]["transition_reward"] == 1.0


def test_the_document_is_json_serializable() -> None:
    import json

    json.dumps(to_atif(_episode()))
