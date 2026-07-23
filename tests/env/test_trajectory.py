from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from rath.env import (
    TRAJECTORY_SCHEMA_VERSION,
    EnvObservation,
    ToolAction,
    TrajectoryEpisode,
    TrajectoryEpisodeEnd,
    TrajectoryEpisodeStart,
    TrajectoryStep,
    load_trajectory_jsonl,
    materialize_trajectory,
    trajectory_to_jsonl,
    write_trajectory_jsonl,
)

_STAMP = "2026-07-12T00:00:00+00:00"


def _observation(chunks=()) -> EnvObservation:  # type: ignore[no-untyped-def]
    return EnvObservation(
        session_id="episode",
        chunks=tuple(chunks),
        latest_tool_result=None,
        sandbox_backend="local",
        lineage={"parent_session_ids": []},
        cumulative_usage=None,
    )


def _step(index: int = 0, *, reward: float = 1.0) -> TrajectoryStep:
    return TrajectoryStep(
        episode_id="episode",
        step_index=index,
        action=ToolAction("tool", {"index": index}),
        transcript_delta=(
            {"kind": "assistant", "payload": {"content": None, "tool_calls": []}},
            {
                "kind": "tool_result",
                "payload": {
                    "tool_call_id": str(index),
                    "name": "tool",
                    "content": json.dumps({"value": index}),
                },
            },
        ),
        tool_result={"value": index},
        reward=reward,
        terminated=False,
        truncated=False,
        created_at=_STAMP,
    )


def _episode(steps=(_step(),), *, status: str = "stopped") -> TrajectoryEpisode:  # type: ignore[no-untyped-def]
    start = TrajectoryEpisodeStart("episode", _observation(), created_at=_STAMP)
    chunks = tuple(row for step in steps for row in step.transcript_delta)
    final = replace(
        _observation(),
        chunks=chunks,
        latest_tool_result={
            "tool_call_id": str(steps[-1].step_index) if steps else "",
            "name": "tool" if steps else "",
            "content": json.dumps({"value": steps[-1].step_index}) if steps else "",
            "content_json": {"value": steps[-1].step_index} if steps else None,
        }
        if steps
        else None,
    )
    end = TrajectoryEpisodeEnd(
        episode_id="episode",
        step_count=len(steps),
        transition_reward=sum(step.reward for step in steps),
        terminal_reward=0.0,
        total_reward=sum(step.reward for step in steps),
        terminated=False,
        truncated=False,
        status=status,
        final_observation=final,
        created_at=_STAMP,
    )
    return TrajectoryEpisode(start, tuple(steps), end)


def test_exact_compact_record_shapes() -> None:
    rows = [json.loads(line) for line in trajectory_to_jsonl(_episode()).splitlines()]
    assert [row["record_type"] for row in rows] == [
        "episode_start",
        "step",
        "episode_end",
    ]
    assert all(row["schema_version"] == TRAJECTORY_SCHEMA_VERSION for row in rows)
    assert all(row["episode_id"] == "episode" for row in rows)
    assert "observation" not in rows[1]
    assert "next_observation" not in rows[1]


def test_trajectory_rejects_mixed_ids_and_non_contiguous_steps() -> None:
    start = TrajectoryEpisodeStart("episode", _observation())
    with pytest.raises(ValueError, match="mixed episode"):
        TrajectoryEpisode(start, (replace(_step(), episode_id="other"),), None)
    with pytest.raises(ValueError, match="contiguous"):
        TrajectoryEpisode(start, (_step(1),), None)


def test_trajectory_rejects_reward_and_count_mismatches() -> None:
    episode = _episode()
    assert episode.end is not None
    with pytest.raises(ValueError, match="step_count"):
        replace(episode, end=replace(episode.end, step_count=2))
    with pytest.raises(ValueError, match="transition_reward"):
        replace(
            episode, end=replace(episode.end, transition_reward=99.0, total_reward=99.0)
        )
    with pytest.raises(ValueError, match="total_reward"):
        replace(episode, end=replace(episode.end, total_reward=99.0))


def test_loader_round_trip_and_allows_eof_incomplete(tmp_path: Path) -> None:
    path = tmp_path / "trajectory.jsonl"
    write_trajectory_jsonl(_episode(), path)
    loaded = load_trajectory_jsonl(path)
    assert loaded == (_episode(),)

    incomplete = tmp_path / "incomplete.jsonl"
    episode = _episode()
    write_trajectory_jsonl((episode.start, *episode.steps), incomplete)
    loaded_incomplete = load_trajectory_jsonl(incomplete)
    assert loaded_incomplete[0].end is None


def test_loader_rejects_future_schema_unknown_type_and_step_before_start(
    tmp_path: Path,
) -> None:
    for name, row, match in [
        (
            "future",
            {
                "schema_version": TRAJECTORY_SCHEMA_VERSION + 1,
                "record_type": "episode_start",
            },
            "future schema_version",
        ),
        (
            "unknown",
            {"schema_version": TRAJECTORY_SCHEMA_VERSION, "record_type": "mystery"},
            "unknown trajectory record_type",
        ),
        ("step", _step().to_jsonable(), "before episode_start"),
    ]:
        path = tmp_path / f"{name}.jsonl"
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match=match):
            load_trajectory_jsonl(path)


def test_loader_rejects_coerced_boolean_protocol_values(tmp_path: Path) -> None:
    path = tmp_path / "bad-bool.jsonl"
    start = TrajectoryEpisodeStart("episode", _observation()).to_jsonable()
    step = _step().to_jsonable()
    step["terminated"] = "false"
    path.write_text(
        json.dumps(start) + "\n" + json.dumps(step) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="terminated must be a boolean"):
        load_trajectory_jsonl(path)


def test_materializer_reconstructs_pre_and_post_observations() -> None:
    episode = _episode((_step(0), _step(1)))
    transitions = materialize_trajectory(episode)
    assert transitions[0].observation == episode.start.initial_observation
    assert len(transitions[0].next_observation.chunks) == 2
    assert transitions[1].observation == transitions[0].next_observation
    assert transitions[-1].next_observation == episode.end.final_observation  # type: ignore[union-attr]


def test_compact_jsonl_growth_is_linear() -> None:
    ten = TrajectoryEpisode(
        TrajectoryEpisodeStart("episode", _observation()),
        tuple(_step(i, reward=0.0) for i in range(10)),
        None,
    )
    hundred = TrajectoryEpisode(
        TrajectoryEpisodeStart("episode", _observation()),
        tuple(_step(i, reward=0.0) for i in range(100)),
        None,
    )
    ratio = len(trajectory_to_jsonl(hundred)) / len(trajectory_to_jsonl(ten))
    assert 7.0 < ratio < 13.0
