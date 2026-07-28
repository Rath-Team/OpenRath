from __future__ import annotations

from uuid import uuid4

from rath.eval import EvaluationResult, Experiment, GateDecision, regression_gate


def _experiment(score: float) -> Experiment:
    return Experiment(
        id=uuid4(),
        dataset_id=uuid4(),
        revision_id=uuid4(),
        results=(
            EvaluationResult(
                evaluator="exact",
                score=score,
                passed=score >= 0.8,
                reason="test",
            ),
        ),
    )


def test_regression_gate_blocks_absolute_and_relative_regression() -> None:
    baseline = _experiment(0.9)
    assert regression_gate(_experiment(0.89), baseline=baseline) is GateDecision.PASS
    assert regression_gate(_experiment(0.85), baseline=baseline) is GateDecision.FAIL
    assert (
        regression_gate(_experiment(0.79), baseline=_experiment(0.7))
        is GateDecision.FAIL
    )
