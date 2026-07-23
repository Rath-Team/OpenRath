from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from rath.env import EnvObservation, RewardResult, ToolAction


@pytest.mark.parametrize("tool_name", ["", "   ", 3, None])
def test_tool_action_rejects_invalid_names(tool_name) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises((TypeError, ValueError)):
        ToolAction(tool_name=tool_name)  # type: ignore[arg-type]


def test_tool_action_requires_mapping_fields() -> None:
    with pytest.raises(TypeError, match="arguments"):
        ToolAction("tool", arguments=[])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="metadata"):
        ToolAction("tool", metadata=[])  # type: ignore[arg-type]


def test_tool_action_snapshots_caller_mappings() -> None:
    arguments = {"nested": {"value": 1}}
    metadata = {"source": "before"}
    action = ToolAction("tool", arguments, metadata)
    arguments["nested"]["value"] = 2
    metadata["source"] = "after"
    assert action.to_jsonable() == {
        "tool_name": "tool",
        "arguments": {"nested": {"value": 1}},
        "metadata": {"source": "before"},
    }


def test_observation_has_explicit_path_uuid_and_bytes_projection() -> None:
    session_id = str(uuid4())
    observation = EnvObservation(
        session_id=session_id,
        chunks=(
            {
                "kind": "user",
                "payload": {
                    "path": Path("workspace/file.txt"),
                    "id": uuid4(),
                    "data": b"abc",
                },
            },
        ),
        latest_tool_result=None,
        sandbox_backend="local",
        lineage={"parent_session_ids": []},
        cumulative_usage={"total_tokens": 3},
    )
    payload = observation.to_jsonable()["chunks"][0]["payload"]
    assert payload["path"] == "workspace/file.txt"
    assert isinstance(payload["id"], str)
    assert payload["data"] == {"__type__": "bytes", "base64": "YWJj"}
    json.dumps(observation.to_jsonable(), allow_nan=False)


def test_observation_rejects_unsupported_protocol_values() -> None:
    with pytest.raises(TypeError, match="unsupported protocol value"):
        EnvObservation(
            session_id="episode",
            chunks=({"kind": "user", "payload": {"bad": object()}},),
            latest_tool_result=None,
            sandbox_backend=None,
            lineage={},
            cumulative_usage=None,
        )


@pytest.mark.parametrize("reward", [float("nan"), float("inf"), -float("inf")])
def test_reward_result_rejects_non_finite_values(reward: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        RewardResult(reward=reward)


def test_reward_result_requires_mapping_info() -> None:
    with pytest.raises(TypeError, match="mapping"):
        RewardResult(info=[])  # type: ignore[arg-type]
