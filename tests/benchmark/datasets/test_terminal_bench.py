from __future__ import annotations

from pathlib import Path

from rath.backend import BackendCapability
from rath.benchmark.datasets import load_terminal_bench

_ROOT = Path(__file__).parent / "fixtures" / "terminal_bench_tasks"
_ALL = frozenset(BackendCapability)
# A container backend that can pull a per-task image but cannot orchestrate several.
_SINGLE_CONTAINER = frozenset(
    {BackendCapability.PER_TASK_IMAGE, BackendCapability.NETWORK_ISOLATION}
)


def test_single_container_task_loads() -> None:
    report = load_terminal_bench(_ROOT, features=_ALL)
    by_id = {task.task_id: task for task in report.tasks}
    task = by_id["swe-bench-astropy-1"]
    assert task.description.strip()  # the instruction text
    assert task.sandbox_spec == "terminal-bench/swe-bench-astropy-1:latest"
    assert task.metadata["dockerfile"].endswith("Dockerfile")


def test_task_id_comes_from_the_directory_name() -> None:
    # task.yaml carries no id field; the directory name is the id.
    report = load_terminal_bench(_ROOT, features=_ALL)
    assert {task.task_id for task in report.tasks} == {
        "swe-bench-astropy-1",
        "ancient-puzzle",
    }


def test_multi_service_task_needs_compose_and_is_skipped_without_it() -> None:
    # Every Terminal-Bench task ships a compose file, but only a few declare more
    # than one service. The service count is the signal, not the file's existence.
    report = load_terminal_bench(_ROOT, features=_SINGLE_CONTAINER)
    assert [task.task_id for task in report.tasks] == ["swe-bench-astropy-1"]
    skipped = {item.task_id: item for item in report.skipped}
    assert BackendCapability.COMPOSE in skipped["ancient-puzzle"].missing
    assert report.coverage == 0.5


def test_single_service_compose_does_not_demand_the_compose_capability() -> None:
    report = load_terminal_bench(_ROOT, features=_SINGLE_CONTAINER)
    assert "swe-bench-astropy-1" not in {item.task_id for item in report.skipped}


def test_timeouts_are_carried_into_metadata() -> None:
    report = load_terminal_bench(_ROOT, features=_ALL)
    task = next(t for t in report.tasks if t.task_id == "swe-bench-astropy-1")
    assert isinstance(task.metadata["max_agent_timeout_sec"], (int, float))


def test_coverage_is_reported_not_hidden() -> None:
    report = load_terminal_bench(_ROOT, features=frozenset())
    assert "coverage" in report.summary()
    assert report.coverage == 0.0
