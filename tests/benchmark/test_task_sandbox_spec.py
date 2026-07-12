from __future__ import annotations

from rath.backend import BackendCapability, BackendSandboxSpec
from rath.benchmark import BenchmarkRunner, BenchmarkTask, CommandVerifier
from rath.env import OpenRathEnvConfig


def _task(**kw: object) -> BenchmarkTask:
    return BenchmarkTask(
        task_id="t1",
        name="t1",
        category="c",
        description="do it",
        language="python",
        metric="pass",
        verifier=CommandVerifier(cmd="true"),
        **kw,  # type: ignore[arg-type]
    )


def test_task_carries_its_own_sandbox_spec() -> None:
    task = _task(sandbox_spec=BackendSandboxSpec(image="python:3.11"))
    assert isinstance(task.sandbox_spec, BackendSandboxSpec)
    assert task.sandbox_spec.image == "python:3.11"


def test_task_requires_per_task_image_when_it_names_one() -> None:
    task = _task(sandbox_spec="python:3.11")
    assert BackendCapability.PER_TASK_IMAGE in task.required_capabilities


def test_online_task_without_an_image_requires_nothing() -> None:
    # internet defaults to False, so only an explicitly online task is unconstrained.
    assert _task(internet=True).required_capabilities == frozenset()


def test_offline_task_requires_network_isolation() -> None:
    offline = _task(internet=False)
    online = _task(internet=True)
    assert BackendCapability.NETWORK_ISOLATION in offline.required_capabilities
    assert BackendCapability.NETWORK_ISOLATION not in online.required_capabilities


def test_runner_opens_the_task_image_over_the_env_default() -> None:
    task = _task(sandbox_spec="python:3.11")
    runner = BenchmarkRunner(
        task,
        env_config=OpenRathEnvConfig(backend="local", sandbox_spec="ubuntu:22.04"),
    )
    assert runner.effective_env_config().sandbox_spec == "python:3.11"


def test_runner_falls_back_to_the_env_default() -> None:
    runner = BenchmarkRunner(
        _task(),
        env_config=OpenRathEnvConfig(backend="local", sandbox_spec="ubuntu:22.04"),
    )
    assert runner.effective_env_config().sandbox_spec == "ubuntu:22.04"
