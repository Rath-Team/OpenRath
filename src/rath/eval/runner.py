"""Offline evaluation runner and baseline regression gate."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from uuid import UUID, uuid4

from rath.eval.models import (
    Dataset,
    EvaluationResult,
    Evaluator,
    Example,
    Experiment,
    GateDecision,
)
from rath.runtime import Run

__all__ = ["EvaluationRunner", "regression_gate"]


class EvaluationRunner:
    async def run(
        self,
        dataset: Dataset,
        *,
        revision_id: UUID,
        execute: Callable[[Example], Awaitable[Run]],
        evaluators: Sequence[Evaluator],
    ) -> Experiment:
        results: list[EvaluationResult] = []
        for example in dataset.examples:
            run = await execute(example)
            for evaluator in evaluators:
                results.append(await evaluator.evaluate(example, run))
        return Experiment(
            id=uuid4(),
            dataset_id=dataset.id,
            revision_id=revision_id,
            results=tuple(results),
        )


def regression_gate(
    candidate: Experiment,
    *,
    baseline: Experiment,
    maximum_regression: float = 0.02,
    minimum_score: float = 0.8,
) -> GateDecision:
    if candidate.mean_score < minimum_score:
        return GateDecision.FAIL
    if candidate.mean_score < baseline.mean_score - maximum_regression:
        return GateDecision.FAIL
    return GateDecision.PASS

