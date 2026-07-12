from __future__ import annotations

from rath.backend import BackendCapability
from rath.benchmark import BenchmarkTask, CommandVerifier, gate_tasks


def _task(task_id: str, **kw: object) -> BenchmarkTask:
    return BenchmarkTask(
        task_id=task_id,
        name=task_id,
        category="c",
        description="d",
        language="python",
        metric="pass",
        verifier=CommandVerifier(cmd="true"),
        **kw,  # type: ignore[arg-type]
    )


def test_gate_keeps_tasks_the_backend_can_run() -> None:
    report = gate_tasks(
        [_task("a")], features=frozenset({BackendCapability.NETWORK_ISOLATION})
    )
    assert [t.task_id for t in report.tasks] == ["a"]
    assert report.skipped == ()
    assert report.coverage == 1.0


def test_gate_skips_and_explains_unrunnable_tasks() -> None:
    report = gate_tasks(
        [_task("needs_image", sandbox_spec="python:3.11", internet=True)],
        features=frozenset(),
    )
    assert report.tasks == ()
    assert len(report.skipped) == 1
    skipped = report.skipped[0]
    assert skipped.task_id == "needs_image"
    assert BackendCapability.PER_TASK_IMAGE in skipped.missing
    assert "per_task_image" in skipped.reason
    assert report.coverage == 0.0


def test_coverage_is_the_runnable_fraction() -> None:
    report = gate_tasks(
        [_task("a", internet=True), _task("b", sandbox_spec="img", internet=True)],
        features=frozenset(),
    )
    assert report.coverage == 0.5


def test_empty_input_is_full_coverage_not_a_zero_division() -> None:
    assert gate_tasks([], features=frozenset()).coverage == 1.0


def test_summary_states_the_coverage() -> None:
    report = gate_tasks([_task("a", internet=True)], features=frozenset())
    assert "1 runnable" in report.summary()
    assert "100%" in report.summary()
