"""Versioned evaluation datasets, results, and experiment summaries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

from rath._json import JSONValue, freeze_mapping
from rath.runtime import Run

__all__ = [
    "Dataset",
    "EvaluationResult",
    "Evaluator",
    "Example",
    "Experiment",
    "GateDecision",
]


@dataclass(frozen=True, slots=True)
class Example:
    id: UUID
    inputs: Mapping[str, JSONValue]
    expected: Mapping[str, JSONValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", freeze_mapping(self.inputs, field="inputs"))
        object.__setattr__(
            self, "expected", freeze_mapping(self.expected, field="expected")
        )

    @classmethod
    def create(
        cls,
        inputs: Mapping[str, object],
        expected: Mapping[str, object],
    ) -> "Example":
        return cls(
            id=uuid4(),
            inputs=freeze_mapping(inputs, field="inputs"),
            expected=freeze_mapping(expected, field="expected"),
        )


@dataclass(frozen=True, slots=True)
class Dataset:
    id: UUID
    name: str
    version: str
    examples: tuple[Example, ...]


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    evaluator: str
    score: float
    passed: bool
    reason: str
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 1:
            raise ValueError("evaluation score must be between 0 and 1")
        object.__setattr__(
            self,
            "metadata",
            freeze_mapping(self.metadata, field="evaluation.metadata"),
        )


@runtime_checkable
class Evaluator(Protocol):
    name: str

    async def evaluate(self, example: Example, run: Run) -> EvaluationResult: ...


@dataclass(frozen=True, slots=True)
class Experiment:
    id: UUID
    dataset_id: UUID
    revision_id: UUID
    results: tuple[EvaluationResult, ...]

    @property
    def mean_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(result.score for result in self.results) / len(self.results)


class GateDecision(str, Enum):
    PASS = "pass"
    FAIL = "fail"
