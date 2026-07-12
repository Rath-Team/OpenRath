from __future__ import annotations

from datetime import datetime

from rath.env import TRAJECTORY_SCHEMA_VERSION, ToolAction, TrajectoryStep


def _step(**kw: object) -> TrajectoryStep:
    return TrajectoryStep(
        episode_id="e",
        step_index=0,
        action=ToolAction("t"),
        transcript_delta=(),
        tool_result=None,
        reward=0.0,
        terminated=False,
        truncated=False,
        **kw,  # type: ignore[arg-type]
    )


def test_schema_version_is_two() -> None:
    assert TRAJECTORY_SCHEMA_VERSION == 2


def test_step_stamps_itself_in_utc() -> None:
    parsed = datetime.fromisoformat(_step().created_at)
    assert parsed.tzinfo is not None
    offset = parsed.utcoffset()
    assert offset is not None and offset.total_seconds() == 0


def test_created_at_survives_the_json_round_trip() -> None:
    step = _step()
    assert step.to_jsonable()["created_at"] == step.created_at


def test_an_explicit_timestamp_is_preserved() -> None:
    stamped = _step(created_at="2026-07-12T00:00:00+00:00")
    assert stamped.created_at == "2026-07-12T00:00:00+00:00"
