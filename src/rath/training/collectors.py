"""Bounded, ordered rollout collectors with true fail-fast behavior."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import replace
from typing import Any, TypeVar
from uuid import uuid4

from rath.benchmark import BenchmarkRunner, BenchmarkRunResult, BenchmarkTask, PolicyFn
from rath.env import (
    EnvObservation,
    OpenRathEnv,
    OpenRathEnvConfig,
    ToolAction,
    TrajectoryEpisode,
    TrajectoryEpisodeEnd,
    TrajectoryEpisodeStart,
    materialize_trajectory,
)
from rath.session import Session
from rath.training.batch import EpisodeRollout, RolloutBatch, RolloutEpisode
from rath.training.errors import TrainingCollectionError

__all__ = ["EnvPolicyFn", "collect_benchmark_rollouts", "collect_env_rollouts"]

EnvInput = str | Session | None
EnvPolicyFn = Callable[[EnvObservation], ToolAction | Mapping[str, Any] | None]
_Input = TypeVar("_Input")
_Output = TypeVar("_Output")


class _FreshEnvFactory:
    __slots__ = ("_factory", "_lock", "_instances")

    def __init__(self, factory: Callable[[], OpenRathEnv]) -> None:
        self._factory = factory
        self._lock = threading.Lock()
        self._instances: list[OpenRathEnv] = []

    def create(self) -> OpenRathEnv:
        env = self._factory()
        if not isinstance(env, OpenRathEnv):
            raise TrainingCollectionError("env_factory must return OpenRathEnv")
        with self._lock:
            if any(existing is env for existing in self._instances):
                raise TrainingCollectionError(
                    "env_factory must return a fresh OpenRathEnv for every episode"
                )
            self._instances.append(env)
        return env


def _bounded_map_ordered(
    values: Iterable[_Input],
    worker: Callable[[int, _Input], _Output],
    *,
    max_workers: int,
    max_in_flight: int,
) -> list[_Output]:
    iterator = iter(values)
    if max_workers == 1:
        return [worker(index, value) for index, value in enumerate(iterator)]

    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures: dict[Future[_Output], int] = {}
    results: dict[int, _Output] = {}
    next_index = 0
    exhausted = False
    failure: BaseException | None = None

    def _submit_one() -> bool:
        nonlocal next_index, exhausted
        if exhausted:
            return False
        try:
            value = next(iterator)
        except StopIteration:
            exhausted = True
            return False
        future = executor.submit(worker, next_index, value)
        futures[future] = next_index
        next_index += 1
        return True

    try:
        while len(futures) < max_in_flight and _submit_one():
            pass
        while futures:
            done, _ = wait(tuple(futures), return_when=FIRST_COMPLETED)
            completed = sorted(done, key=lambda future: futures[future])
            for future in completed:
                index = futures.pop(future)
                try:
                    results[index] = future.result()
                except BaseException as exc:
                    failure = exc
                    break
            if failure is not None:
                for pending in futures:
                    pending.cancel()
                break
            while len(futures) < max_in_flight and _submit_one():
                pass
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    if failure is not None:
        raise failure
    return [results[index] for index in range(next_index)]


def _error_mapping(exc: BaseException, phase: str) -> dict[str, Any]:
    return {"phase": phase, "type": type(exc).__name__, "message": str(exc)}


def _error_text(error: Mapping[str, Any] | None) -> str | None:
    if error is None:
        return None
    message = error.get("message")
    return str(message) if message is not None else json.dumps(dict(error))


def _synthetic_trajectory(
    *,
    status: str,
    error: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> TrajectoryEpisode:
    episode_id = f"collection-failure-{uuid4()}"
    observation = EnvObservation(
        session_id=episode_id,
        chunks=(),
        latest_tool_result=None,
        sandbox_backend=None,
        lineage={"parent_session_ids": []},
        cumulative_usage=None,
    )
    start = TrajectoryEpisodeStart(episode_id, observation, metadata)
    end = TrajectoryEpisodeEnd(
        episode_id=episode_id,
        step_count=0,
        transition_reward=0.0,
        terminal_reward=0.0,
        total_reward=0.0,
        terminated=False,
        truncated=False,
        status=status,
        final_observation=observation,
        error=error,
    )
    return TrajectoryEpisode(start, (), end)


def _normalize_trajectory_status(
    trajectory: TrajectoryEpisode,
    *,
    status: str,
    error: Mapping[str, Any] | None,
) -> TrajectoryEpisode:
    end = trajectory.end
    if end is None:
        transitions = materialize_trajectory(trajectory)
        final = (
            trajectory.start.initial_observation
            if not transitions
            else transitions[-1].next_observation
        )
        transition_reward = float(sum(step.reward for step in trajectory.steps))
        end = TrajectoryEpisodeEnd(
            episode_id=trajectory.episode_id,
            step_count=len(trajectory.steps),
            transition_reward=transition_reward,
            terminal_reward=0.0,
            total_reward=transition_reward,
            terminated=False,
            truncated=False,
            status=status,
            final_observation=final,
            error=error,
        )
    elif end.status != status:
        end = replace(end, status=status, error=error)
    return TrajectoryEpisode(trajectory.start, trajectory.steps, end)


def _episode_rollout(
    trajectory: TrajectoryEpisode,
    *,
    task_id: str | None,
    metadata: Mapping[str, Any] | None = None,
    error: str | None = None,
) -> EpisodeRollout:
    end = trajectory.end
    assert end is not None
    summary = RolloutEpisode(
        episode_id=trajectory.episode_id,
        task_id=task_id,
        reward=end.total_reward,
        terminated=end.terminated,
        truncated=end.truncated,
        steps=len(trajectory.steps),
        status=end.status,
        metadata={} if metadata is None else metadata,
        error=error,
    )
    return EpisodeRollout(summary, trajectory)


def _collect_one_env_rollout(
    index: int,
    episode_input: EnvInput,
    policy: EnvPolicyFn,
    *,
    factory: _FreshEnvFactory,
    max_steps: int,
    fail_fast: bool,
) -> EpisodeRollout:
    env: OpenRathEnv | None = None
    observation: EnvObservation | None = None
    phase = "setup"
    try:
        env = factory.create()
        observation = env.reset(episode_input)
        while env.step_count < max_steps:
            phase = "policy"
            action = policy(observation)
            if action is None:
                env.finish(status="stopped")
                break
            phase = "environment"
            result = env.step(action)
            observation = result.observation
            if result.done:
                break
        else:
            if env.state == "running":
                env.finish(status="max_steps", truncated=True)
        trajectory = env.trajectory_episode
        assert trajectory is not None and trajectory.end is not None
        return _episode_rollout(
            trajectory,
            task_id=None,
            metadata={"input_index": index},
        )
    except Exception as exc:
        if env is not None and env.state == "running":
            try:
                env.finish(
                    status=f"{phase}_failed",
                    error=_error_mapping(exc, phase),
                    abandon=True,
                )
            except Exception:
                pass
        if fail_fast:
            raise
        error = _error_mapping(exc, phase)
        trajectory = None if env is None else env.trajectory_episode
        if trajectory is None:
            trajectory = _synthetic_trajectory(
                status=f"{phase}_failed",
                error=error,
                metadata={"input_index": index},
            )
        elif trajectory.end is None or trajectory.end.status != f"{phase}_failed":
            trajectory = _normalize_trajectory_status(
                trajectory, status=f"{phase}_failed", error=error
            )
        return _episode_rollout(
            trajectory,
            task_id=None,
            metadata={"input_index": index, "failed_phase": phase},
            error=str(exc),
        )
    finally:
        if env is not None:
            env.close()


def collect_env_rollouts(
    episode_inputs: Iterable[EnvInput],
    policy: EnvPolicyFn,
    *,
    env_config: OpenRathEnvConfig | None = None,
    env_factory: Callable[[], OpenRathEnv] | None = None,
    max_steps: int = 64,
    max_workers: int = 1,
    max_in_flight: int | None = None,
    fail_fast: bool = True,
    meta_info: Mapping[str, Any] | None = None,
) -> RolloutBatch:
    if env_config is not None and env_factory is not None:
        raise ValueError("pass env_config or env_factory, not both")
    _validate_collection_args(max_steps, max_workers, max_in_flight)
    in_flight = max_workers if max_in_flight is None else max_in_flight
    factory = _FreshEnvFactory(
        env_factory if env_factory is not None else lambda: OpenRathEnv(env_config)
    )
    rollouts = _bounded_map_ordered(
        episode_inputs,
        lambda index, value: _collect_one_env_rollout(
            index,
            value,
            policy,
            factory=factory,
            max_steps=max_steps,
            fail_fast=fail_fast,
        ),
        max_workers=max_workers,
        max_in_flight=in_flight,
    )
    return RolloutBatch(
        tuple(rollouts),
        meta_info={
            "collector": "collect_env_rollouts",
            "max_steps": max_steps,
            "max_workers": max_workers,
            "max_in_flight": in_flight,
            "fail_fast": fail_fast,
            **dict(meta_info or {}),
        },
    )


def _rollout_from_benchmark_result(
    result: BenchmarkRunResult, index: int
) -> EpisodeRollout:
    error_mapping = result.error
    trajectory = result.trajectory_episode
    if trajectory is None:
        trajectory = _synthetic_trajectory(
            status=result.status,
            error=(
                {"phase": result.status, "message": "benchmark setup failed"}
                if error_mapping is None
                else error_mapping
            ),
            metadata={"task_id": result.task.task_id},
        )
    elif trajectory.end is None or trajectory.end.status != result.status:
        trajectory = _normalize_trajectory_status(
            trajectory,
            status=result.status,
            error=error_mapping,
        )
    return _episode_rollout(
        trajectory,
        task_id=result.task.task_id,
        metadata={
            "input_index": index,
            "category": result.task.category,
            "language": result.task.language,
            "metric": result.task.metric,
            "passed": result.passed,
            "score": result.score,
        },
        error=_error_text(error_mapping),
    )


def collect_benchmark_rollouts(
    tasks: Iterable[BenchmarkTask],
    policy: PolicyFn,
    *,
    env_config: OpenRathEnvConfig | None = None,
    max_workers: int = 1,
    max_in_flight: int | None = None,
    fail_fast: bool = True,
    meta_info: Mapping[str, Any] | None = None,
) -> RolloutBatch:
    _validate_collection_args(1, max_workers, max_in_flight)
    in_flight = max_workers if max_in_flight is None else max_in_flight

    def _worker(index: int, task: BenchmarkTask) -> EpisodeRollout:
        result = BenchmarkRunner(task, env_config=env_config).run(
            policy, fail_fast=fail_fast
        )
        return _rollout_from_benchmark_result(result, index)

    rollouts = _bounded_map_ordered(
        tasks,
        _worker,
        max_workers=max_workers,
        max_in_flight=in_flight,
    )
    return RolloutBatch(
        tuple(rollouts),
        meta_info={
            "collector": "collect_benchmark_rollouts",
            "max_workers": max_workers,
            "max_in_flight": in_flight,
            "fail_fast": fail_fast,
            **dict(meta_info or {}),
        },
    )


def _validate_collection_args(
    max_steps: int, max_workers: int, max_in_flight: int | None
) -> None:
    if max_steps <= 0:
        raise ValueError("max_steps must be positive")
    if max_workers <= 0:
        raise ValueError("max_workers must be positive")
    if max_in_flight is not None and max_in_flight <= 0:
        raise ValueError("max_in_flight must be positive")
