from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from rath.benchmark import BenchmarkTask, PytestVerifier
from rath.env import OpenRathEnv, OpenRathEnvConfig, ToolAction
from rath.training import (
    TrainingCollectionError,
    collect_benchmark_rollouts,
    collect_env_rollouts,
)


def _task(task_id: str = "task") -> BenchmarkTask:
    return BenchmarkTask(
        task_id=task_id,
        name=task_id,
        category="software",
        description="Implement add_one.",
        language="Python",
        metric="pass",
        initial_files={
            "solution.py": "def add_one(x):\n    return x\n",
            "test_solution.py": (
                "from solution import add_one\n"
                "def test_add_one(): assert add_one(1) == 2\n"
            ),
        },
        verifier=PytestVerifier(),
        max_steps=1,
    )


def _fix_action() -> ToolAction:
    return ToolAction(
        "write_workspace_file",
        {"path": "solution.py", "content": "def add_one(x):\n    return x + 1\n"},
    )


def test_env_collection_is_ordered_with_concurrency() -> None:
    batch = collect_env_rollouts(
        ["first", "second", "third"],
        lambda observation: None,
        env_config=OpenRathEnvConfig(backend="local"),
        max_workers=2,
    )
    assert [
        rollout.trajectory.start.initial_observation.chunks[0]["payload"]["content"]
        for rollout in batch.rollouts
    ] == ["first", "second", "third"]
    assert [episode.metadata["input_index"] for episode in batch.episodes] == [0, 1, 2]


def test_collector_bounds_generator_consumption() -> None:
    pulled: list[int] = []
    entered = 0
    lock = threading.Lock()
    all_entered = threading.Event()
    release = threading.Event()

    def _inputs():  # type: ignore[no-untyped-def]
        for index in range(10):
            pulled.append(index)
            yield str(index)

    def _policy(observation):  # type: ignore[no-untyped-def]
        nonlocal entered
        with lock:
            entered += 1
            if entered == 2:
                all_entered.set()
        assert release.wait(2)
        return None

    with ThreadPoolExecutor(max_workers=1) as driver:
        future = driver.submit(
            collect_env_rollouts,
            _inputs(),
            _policy,
            env_config=OpenRathEnvConfig(backend="local"),
            max_workers=2,
            max_in_flight=2,
        )
        assert all_entered.wait(2)
        assert pulled == [0, 1]
        release.set()
        assert future.result().num_episodes == 10


def test_fail_fast_stops_pulling_and_waits_for_running_cleanup() -> None:
    pulled: list[str] = []
    slow_entered = threading.Event()
    failure_seen = threading.Event()
    release_slow = threading.Event()

    def _inputs():  # type: ignore[no-untyped-def]
        for value in ["slow", "boom", "never-1", "never-2"]:
            pulled.append(value)
            yield value

    def _policy(observation):  # type: ignore[no-untyped-def]
        value = observation.chunks[0]["payload"]["content"]
        if value == "slow":
            slow_entered.set()
            assert release_slow.wait(2)
            return None
        if value == "boom":
            assert slow_entered.wait(2)
            failure_seen.set()
            raise RuntimeError("policy failed quickly")
        return None

    with ThreadPoolExecutor(max_workers=1) as driver:
        future = driver.submit(
            collect_env_rollouts,
            _inputs(),
            _policy,
            env_config=OpenRathEnvConfig(backend="local"),
            max_workers=2,
            max_in_flight=2,
            fail_fast=True,
        )
        assert failure_seen.wait(2)
        time.sleep(0.05)
        assert pulled == ["slow", "boom"]
        release_slow.set()
        with pytest.raises(RuntimeError, match="policy failed quickly"):
            future.result()


def test_non_fast_policy_failure_retains_executed_steps() -> None:
    calls = 0

    def _policy(observation):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 1:
            return ToolAction(
                "write_workspace_file", {"path": "answer.txt", "content": "done"}
            )
        raise RuntimeError("policy crashed after action")

    batch = collect_env_rollouts(
        ["task"],
        _policy,
        env_config=OpenRathEnvConfig(backend="local"),
        fail_fast=False,
    )
    rollout = batch.rollouts[0]
    assert rollout.episode.status == "policy_failed"
    assert rollout.episode.error == "policy crashed after action"
    assert len(rollout.trajectory.steps) == 1


def test_env_factory_must_be_fresh_and_is_mutually_exclusive_with_config() -> None:
    shared = OpenRathEnv(OpenRathEnvConfig(backend="local"))
    with pytest.raises(TrainingCollectionError, match="fresh"):
        collect_env_rollouts(
            ["one", "two"],
            lambda observation: None,
            env_factory=lambda: shared,
        )
    with pytest.raises(ValueError, match="not both"):
        collect_env_rollouts(
            [],
            lambda observation: None,
            env_config=OpenRathEnvConfig(backend="local"),
            env_factory=lambda: OpenRathEnv(),
        )


def test_benchmark_collection_builds_valid_episode_rollouts() -> None:
    batch = collect_benchmark_rollouts(
        [_task("a"), _task("b")],
        lambda task, observation: _fix_action(),
        env_config=OpenRathEnvConfig(backend="local"),
        max_workers=2,
    )
    assert [episode.task_id for episode in batch.episodes] == ["a", "b"]
    assert all(episode.status == "completed" for episode in batch.episodes)
    assert all(episode.reward == 1.0 for episode in batch.episodes)


def test_benchmark_non_fast_policy_failure_is_retained() -> None:
    def _policy(task: BenchmarkTask, observation: Any):
        raise RuntimeError("benchmark policy crashed")

    batch = collect_benchmark_rollouts(
        [_task()],
        _policy,
        env_config=OpenRathEnvConfig(backend="local"),
        fail_fast=False,
    )
    assert batch.episodes[0].status == "policy_failed"
    assert batch.episodes[0].error == "benchmark policy crashed"
