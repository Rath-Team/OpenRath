from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from rath.env import (
    OpenRathEnv,
    OpenRathEnvConfig,
    RewardResult,
    ToolAction,
    load_trajectory_jsonl,
    materialize_trajectory,
)
from rath.flow.tool import FlowToolCall
from rath.session import ChunkKind, Session, load_session, session_registry
from rath.session.persistence.paths import session_file


class AddOneTool(FlowToolCall):
    @property
    def name(self) -> str:
        return "add_one"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {"type": "object"}

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> int:
        return int(arguments["x"]) + 1


def _env(**kwargs: Any) -> OpenRathEnv:
    return OpenRathEnv(
        OpenRathEnvConfig(backend="local", tools=[AddOneTool()], **kwargs)
    )


def test_default_config_uses_opensandbox() -> None:
    assert OpenRathEnvConfig().backend == "opensandbox"


def test_reset_does_not_mutate_session_registry() -> None:
    registry = session_registry()
    before = registry.get_active_id()
    env = _env()
    try:
        observation = env.reset("solve this")
        assert observation.chunks[0]["payload"]["content"] == "solve this"
        assert registry.get_active_id() == before
        assert env.session is not None
        assert registry.get(env.session.id) is None
    finally:
        env.close()


def test_reset_from_session_forks_without_mutating_source() -> None:
    source = Session.create("user", "seed")
    env = _env()
    try:
        observation = env.reset(source)
        assert env.session is not source
        assert source.sandbox_backend is None
        assert observation.lineage["parent_session_ids"] == [str(source.id)]
    finally:
        env.close()


def test_step_records_compact_delta_and_o1_step_count() -> None:
    env = _env()
    try:
        initial = env.reset("increment")
        result = env.step(ToolAction("add_one", {"x": 41}))
        assert env.step_count == 1
        assert result.reward == 0.0
        assert result.done is False
        assert result.observation.latest_tool_result["content_json"] == 42  # type: ignore[index]
        step = env.trajectory[0]
        assert step.step_index == 0
        assert len(step.transcript_delta) == 2
        assert len(initial.chunks) + len(step.transcript_delta) == len(
            result.observation.chunks
        )
        assert step.tool_result == {"value": 42}
    finally:
        env.close()


def test_reward_termination_and_max_step_truncation() -> None:
    terminal = _env(
        reward_fn=lambda _session, _action, raw: RewardResult(
            reward=float(raw), done=True
        )
    )
    terminal.reset("increment")
    result = terminal.step(ToolAction("add_one", {"x": 2}))
    assert result.terminated and not result.truncated
    assert terminal.trajectory_episode.end.status == "completed"  # type: ignore[union-attr]
    terminal.close()

    truncated = _env(max_steps=1)
    truncated.reset("increment")
    result = truncated.step(ToolAction("add_one", {"x": 2}))
    assert result.truncated and not result.terminated
    assert truncated.trajectory_episode.end.status == "max_steps"  # type: ignore[union-attr]
    truncated.close()


def test_trajectory_path_appends_multiple_episodes(tmp_path: Path) -> None:
    path = tmp_path / "rollouts.jsonl"
    env = _env(trajectory_path=path, max_steps=1)
    env.reset("first")
    env.step(ToolAction("add_one", {"x": 1}))
    env.reset("second")
    env.step(ToolAction("add_one", {"x": 2}))
    env.close()
    episodes = load_trajectory_jsonl(path)
    assert len(episodes) == 2
    assert [episode.steps[0].tool_result for episode in episodes] == [
        {"value": 2},
        {"value": 3},
    ]
    assert materialize_trajectory(episodes[1])[-1].next_observation == (
        episodes[1].end.final_observation
    )


def test_export_trajectory_after_close(tmp_path: Path) -> None:
    env = _env(max_steps=1)
    env.reset("increment")
    env.step(ToolAction("add_one", {"x": 9}))
    env.close()
    path = tmp_path / "export.jsonl"
    env.export_trajectory_jsonl(path)
    assert load_trajectory_jsonl(path)[0].steps[0].action.arguments == {"x": 9}


def test_unknown_tool_does_not_start_a_step() -> None:
    env = _env()
    try:
        env.reset("unknown")
        with pytest.raises(ValueError, match="unknown tool"):
            env.step(ToolAction("missing", {}))
        assert env.step_count == 0
        assert env.trajectory == ()
    finally:
        env.close()


def test_session_wal_is_closed_on_terminal_episode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENRATH_HOME", str(tmp_path))
    env = _env(persist_trajectory=True, max_steps=1)
    env.reset("persist")
    env.step(ToolAction("add_one", {"x": 4}))
    assert env.session is not None
    persisted = load_session(env.session.id, path=session_file(env.session.id))
    assert persisted.closed is True
    assert [row.kind for row in persisted.chunk_table.rows] == [
        ChunkKind.USER,
        ChunkKind.ASSISTANT,
        ChunkKind.TOOL_RESULT,
    ]
    assert json.loads(persisted.chunk_table.rows[-1].payload["content"]) == 5
    env.close()
