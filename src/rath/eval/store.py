"""Durable evaluation dataset and experiment stores."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from rath._json import thaw_json
from rath.eval.models import Dataset, EvaluationResult, Example, Experiment
from rath.runtime import PostgresRunStore, SQLiteRunStore

__all__ = [
    "EvaluationStore",
    "PostgresEvaluationStore",
    "SQLiteEvaluationStore",
]


def _dataset_json(dataset: Dataset) -> list[dict[str, object]]:
    return [
        {
            "id": str(example.id),
            "inputs": thaw_json(example.inputs),
            "expected": thaw_json(example.expected),
        }
        for example in dataset.examples
    ]


def _results_json(experiment: Experiment) -> list[dict[str, object]]:
    return [
        {
            "evaluator": result.evaluator,
            "score": result.score,
            "passed": result.passed,
            "reason": result.reason,
            "metadata": thaw_json(result.metadata),
        }
        for result in experiment.results
    ]


def _dataset(row: Mapping[str, Any]) -> Dataset:
    values = row["examples_json"]
    if isinstance(values, str):
        values = json.loads(values)
    return Dataset(
        id=UUID(str(row["id"])),
        name=row["name"],
        version=row["version"],
        examples=tuple(
            Example(
                id=UUID(item["id"]),
                inputs=item["inputs"],
                expected=item["expected"],
            )
            for item in values
        ),
    )


def _experiment(row: Mapping[str, Any]) -> Experiment:
    values = row["results_json"]
    if isinstance(values, str):
        values = json.loads(values)
    return Experiment(
        id=UUID(str(row["id"])),
        dataset_id=UUID(str(row["dataset_id"])),
        revision_id=UUID(str(row["revision_id"])),
        results=tuple(
            EvaluationResult(
                evaluator=item["evaluator"],
                score=float(item["score"]),
                passed=bool(item["passed"]),
                reason=item["reason"],
                metadata=item["metadata"],
            )
            for item in values
        ),
    )


@runtime_checkable
class EvaluationStore(Protocol):
    def save_dataset(self, dataset: Dataset) -> Dataset: ...

    def get_dataset(self, dataset_id: UUID) -> Dataset: ...

    def save_experiment(self, experiment: Experiment) -> Experiment: ...

    def get_experiment(self, experiment_id: UUID) -> Experiment: ...


class SQLiteEvaluationStore:
    def __init__(self, run_store: SQLiteRunStore) -> None:
        self.path = str(run_store.path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def save_dataset(self, dataset: Dataset) -> Dataset:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO evaluation_datasets(id, name, version, examples_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name, version) DO UPDATE
                SET examples_json = excluded.examples_json
                """,
                (
                    str(dataset.id),
                    dataset.name,
                    dataset.version,
                    json.dumps(_dataset_json(dataset), separators=(",", ":")),
                ),
            )
        return dataset

    def get_dataset(self, dataset_id: UUID) -> Dataset:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM evaluation_datasets WHERE id = ?",
                (str(dataset_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(dataset_id))
        return _dataset(row)

    def save_experiment(self, experiment: Experiment) -> Experiment:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO evaluation_experiments(
                    id, dataset_id, revision_id, results_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(experiment.id),
                    str(experiment.dataset_id),
                    str(experiment.revision_id),
                    json.dumps(_results_json(experiment), separators=(",", ":")),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return experiment

    def get_experiment(self, experiment_id: UUID) -> Experiment:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM evaluation_experiments WHERE id = ?",
                (str(experiment_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(experiment_id))
        return _experiment(row)


class PostgresEvaluationStore:
    def __init__(self, run_store: PostgresRunStore) -> None:
        self.run_store = run_store

    def save_dataset(self, dataset: Dataset) -> Dataset:
        from psycopg.types.json import Jsonb

        with self.run_store.connection() as connection:
            connection.execute(
                """
                INSERT INTO evaluation_datasets(id, name, version, examples_json)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(name, version) DO UPDATE
                SET examples_json = excluded.examples_json
                """,
                (dataset.id, dataset.name, dataset.version, Jsonb(_dataset_json(dataset))),
            )
        return dataset

    def get_dataset(self, dataset_id: UUID) -> Dataset:
        with self.run_store.connection() as connection:
            row = connection.execute(
                "SELECT * FROM evaluation_datasets WHERE id = %s", (dataset_id,)
            ).fetchone()
        if row is None:
            raise KeyError(str(dataset_id))
        return _dataset(row)

    def save_experiment(self, experiment: Experiment) -> Experiment:
        from psycopg.types.json import Jsonb

        with self.run_store.connection() as connection:
            connection.execute(
                """
                INSERT INTO evaluation_experiments(
                    id, dataset_id, revision_id, results_json
                ) VALUES (%s, %s, %s, %s)
                """,
                (
                    experiment.id,
                    experiment.dataset_id,
                    experiment.revision_id,
                    Jsonb(_results_json(experiment)),
                ),
            )
        return experiment

    def get_experiment(self, experiment_id: UUID) -> Experiment:
        with self.run_store.connection() as connection:
            row = connection.execute(
                "SELECT * FROM evaluation_experiments WHERE id = %s",
                (experiment_id,),
            ).fetchone()
        if row is None:
            raise KeyError(str(experiment_id))
        return _experiment(row)
