"""Typed lifecycle and persistence errors for :mod:`rath.env`."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

__all__ = [
    "EnvSetupError",
    "EnvStepError",
    "TrajectoryPersistenceError",
]


class _EnvError(RuntimeError):
    __slots__ = ("phase", "context", "cleanup_errors")

    def __init__(
        self,
        message: str,
        *,
        phase: str,
        context: Mapping[str, Any] | None = None,
        cleanup_errors: Sequence[BaseException] = (),
    ) -> None:
        super().__init__(message)
        self.phase = phase
        self.context = dict(context or {})
        self.cleanup_errors = tuple(cleanup_errors)


class EnvSetupError(_EnvError):
    """Raised when an episode cannot be reset transactionally."""


class EnvStepError(_EnvError):
    """Raised after a started action fails and its partial step is retained."""

    __slots__ = ("step",)

    def __init__(self, *args: Any, step: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.step = step


class TrajectoryPersistenceError(_EnvError):
    """Raised when a compact trajectory record cannot be persisted."""
