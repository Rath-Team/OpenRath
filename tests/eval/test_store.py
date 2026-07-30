from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from rath.eval import (
    Dataset,
    EvaluationResult,
    Example,
    Experiment,
    SQLiteEvaluationStore,
)
from rath.runtime import SQLiteRunStore


def test_evaluation_dataset_and_experiment_persist(tmp_path: Path) -> None:
    run_store = SQLiteRunStore(tmp_path / "runtime.db")
    store = SQLiteEvaluationStore(run_store)
    dataset = Dataset(
        id=uuid4(),
        name="qa",
        version="1",
        examples=(Example.create({"question": "q"}, {"answer": "a"}),),
    )
    experiment = Experiment(
        id=uuid4(),
        dataset_id=dataset.id,
        revision_id=uuid4(),
        results=(
            EvaluationResult(
                evaluator="exact",
                score=1,
                passed=True,
                reason="match",
            ),
        ),
    )
    store.save_dataset(dataset)
    store.save_experiment(experiment)

    assert store.get_dataset(dataset.id) == dataset
    assert store.get_experiment(experiment.id) == experiment
