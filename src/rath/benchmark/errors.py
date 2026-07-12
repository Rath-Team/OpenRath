"""Typed benchmark setup, policy, and verifier errors."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = [
    "BenchmarkError",
    "BenchmarkSetupError",
    "VerifierExecutionError",
]


class BenchmarkError(RuntimeError):
    __slots__ = ("task_id", "phase", "context")

    def __init__(
        self,
        message: str,
        *,
        task_id: str,
        phase: str,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.task_id = task_id
        self.phase = phase
        self.context = dict(context or {})


class BenchmarkSetupError(BenchmarkError):
    __slots__ = ("path", "backend_failure")

    def __init__(
        self,
        message: str,
        *,
        task_id: str,
        path: str,
        backend_failure: Mapping[str, Any],
    ) -> None:
        super().__init__(
            message,
            task_id=task_id,
            phase="setup",
            context={"path": path, "backend_failure": dict(backend_failure)},
        )
        self.path = path
        self.backend_failure = dict(backend_failure)


class VerifierExecutionError(BenchmarkError):
    """Verifier command could not be executed; this is not a failed assertion."""
