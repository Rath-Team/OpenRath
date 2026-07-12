from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

import rath.env.core as env_core
from rath.backend import get
from rath.env import (
    EnvSetupError,
    EnvStepError,
    OpenRathEnv,
    OpenRathEnvConfig,
    RewardResult,
    ToolAction,
    load_trajectory_jsonl,
)
from rath.flow.tool import FlowToolCall
from rath.session import Session, session_registry


class _Tool(FlowToolCall):
    @property
    def name(self) -> str:
        return "write"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {"type": "object"}

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> Any:
        return {"ok": True}


def _env(**kwargs: Any) -> OpenRathEnv:
    return OpenRathEnv(OpenRathEnvConfig(backend="local", tools=[_Tool()], **kwargs))


@pytest.mark.parametrize(
    "target",
    [
        "rath.env.core.observation_from_session",
        "rath.env.core.JsonlAppendWriter.append",
    ],
)
def test_reset_rolls_back_setup_failure_and_can_retry(
    target: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = get("local")
    before = backend.sandbox_count()
    env = _env(trajectory_path=tmp_path / "trajectory.jsonl")
    if target.endswith("JsonlAppendWriter.append"):
        owner = env_core.JsonlAppendWriter
        name = "append"
    else:
        owner = env_core
        name = "observation_from_session"
    original_value = getattr(owner, name)

    def _fail(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("injected setup failure")

    monkeypatch.setattr(owner, name, _fail)
    with pytest.raises(EnvSetupError) as caught:
        env.reset("task")
    assert caught.value.__cause__ is not None
    assert env.state == "new"
    assert backend.sandbox_count() == before
    monkeypatch.setattr(owner, name, original_value)
    env.reset("retry")
    env.close()


def test_reward_failure_retains_action_result_delta_and_faults() -> None:
    def _reward(*args: Any) -> RewardResult:
        raise RuntimeError("verifier crashed")

    env = _env(reward_fn=_reward)
    env.reset("task")
    with pytest.raises(EnvStepError) as caught:
        env.step(ToolAction("write", {}))
    step = caught.value.step
    assert step.step_index == 0
    assert step.action.tool_name == "write"
    assert len(step.transcript_delta) == 2
    assert step.tool_result == {"ok": True}
    assert step.status == "failed"
    assert env.step_count == 1
    assert env.state == "faulted"
    assert env.session is not None and env.session.sandbox is None
    with pytest.raises(RuntimeError, match="faulted"):
        env.step(ToolAction("write", {}))
    env.reset("retry")
    assert env.step_count == 0
    env.close()


class _SpyWriter:
    instances: list["_SpyWriter"] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.closed = 0
        self.abandoned = 0
        self.instances.append(self)

    def write_chunk(self, index: int, row: Any) -> None:
        pass

    def close(self) -> None:
        self.closed += 1

    def abandon(self) -> None:
        self.abandoned += 1


def test_writer_close_vs_abandon(monkeypatch: pytest.MonkeyPatch) -> None:
    _SpyWriter.instances.clear()
    monkeypatch.setattr("rath.env.core.SessionWriter", _SpyWriter)
    terminal = _env(persist_trajectory=True, max_steps=1)
    terminal.reset("task")
    terminal.step(ToolAction("write", {}))
    terminal.close()
    assert (_SpyWriter.instances[0].closed, _SpyWriter.instances[0].abandoned) == (
        1,
        0,
    )

    interrupted = _env(persist_trajectory=True)
    interrupted.reset("task")
    interrupted.close()
    assert (_SpyWriter.instances[1].closed, _SpyWriter.instances[1].abandoned) == (
        0,
        1,
    )


def test_shared_trajectory_output_never_truncates(tmp_path: Path) -> None:
    path = tmp_path / "shared.jsonl"

    def _run(index: int) -> None:
        env = _env(trajectory_path=path, max_steps=1)
        env.reset(f"task-{index}")
        env.step(ToolAction("write", {}))
        env.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(_run, range(4)))
    episodes = load_trajectory_jsonl(path)
    assert len(episodes) == 4
    assert all(episode.end is not None for episode in episodes)


def test_step_persistence_failure_leaves_reloadable_incomplete_episode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = env_core.JsonlAppendWriter.append
    calls = 0

    def _fail_second(self: Any, records: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected step write failure")
        original(self, records)

    monkeypatch.setattr(env_core.JsonlAppendWriter, "append", _fail_second)
    path = tmp_path / "partial.jsonl"
    env = _env(trajectory_path=path)
    env.reset("task")
    with pytest.raises(EnvStepError, match="trajectory_step_persistence"):
        env.step(ToolAction("write", {}))
    assert len(env.trajectory) == 1
    env.close()

    loaded = load_trajectory_jsonl(path)
    assert len(loaded) == 1
    assert loaded[0].steps == ()
    assert loaded[0].end is None


def test_shared_unsafe_tool_does_not_overlap_across_envs() -> None:
    lock = threading.Lock()

    class _Unsafe(_Tool):
        def __init__(self) -> None:
            self.in_flight = 0
            self.peak = 0

        def __call__(self, session: Session, arguments: Mapping[str, Any]) -> Any:
            with lock:
                self.in_flight += 1
                self.peak = max(self.peak, self.in_flight)
            time.sleep(0.05)
            with lock:
                self.in_flight -= 1
            return {"ok": True}

    tool = _Unsafe()

    def _run(index: int) -> None:
        env = OpenRathEnv(OpenRathEnvConfig(backend="local", tools=[tool], max_steps=1))
        env.reset(str(index))
        env.step(ToolAction("write", {}))
        env.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_run, range(4)))
    assert tool.peak == 1


def test_registry_state_is_unchanged_across_full_lifecycle() -> None:
    registry = session_registry()
    before = registry.get_active_id()
    env = _env(max_steps=1)
    env.reset("task")
    env.step(ToolAction("write", {}))
    env.close()
    assert registry.get_active_id() == before
