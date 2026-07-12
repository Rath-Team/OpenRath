"""Typed training batch, collection, and optional-adapter errors."""

from __future__ import annotations

__all__ = ["TrainingAdapterError", "TrainingBatchError", "TrainingCollectionError"]


class TrainingBatchError(ValueError):
    """Rollout ownership or summary invariants are invalid."""


class TrainingCollectionError(RuntimeError):
    """Rollout collection configuration or factory behavior is invalid."""


class TrainingAdapterError(RuntimeError):
    """An optional trainer adapter is missing or API-incompatible."""
