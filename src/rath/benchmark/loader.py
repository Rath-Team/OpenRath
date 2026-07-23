"""Answer "can this task run on this backend?" before an episode starts.

A loader that quietly drops the tasks it cannot run publishes a score computed over
a subset it never names. Every skip is counted and reasoned here instead, so a
coverage gap reads as a coverage gap rather than as a mystery failure halfway
through a rollout.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from rath.backend import BackendCapability
from rath.benchmark.task import BenchmarkTask

__all__ = ["LoaderReport", "SkippedTask", "gate_tasks"]


@dataclass(frozen=True, slots=True)
class SkippedTask:
    """A task this backend cannot run, and what it would have taken."""

    task_id: str
    missing: frozenset[BackendCapability]

    @property
    def reason(self) -> str:
        names = ", ".join(sorted(capability.value for capability in self.missing))
        return f"backend lacks: {names}"


@dataclass(frozen=True, slots=True)
class LoaderReport:
    """Runnable tasks plus an explicit account of everything left out."""

    tasks: tuple[BenchmarkTask, ...] = ()
    skipped: tuple[SkippedTask, ...] = ()

    @property
    def coverage(self) -> float:
        total = len(self.tasks) + len(self.skipped)
        return 1.0 if total == 0 else len(self.tasks) / total

    def summary(self) -> str:
        return (
            f"{len(self.tasks)} runnable, {len(self.skipped)} skipped "
            f"({self.coverage:.0%} coverage)"
        )


def gate_tasks(
    tasks: Iterable[BenchmarkTask],
    *,
    features: frozenset[BackendCapability],
) -> LoaderReport:
    """Partition ``tasks`` by whether ``features`` satisfies what each one needs."""

    runnable: list[BenchmarkTask] = []
    skipped: list[SkippedTask] = []
    for task in tasks:
        missing = task.required_capabilities - features
        if missing:
            skipped.append(SkippedTask(task.task_id, frozenset(missing)))
        else:
            runnable.append(task)
    return LoaderReport(tuple(runnable), tuple(skipped))
