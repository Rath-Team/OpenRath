"""Explicit durable step and router boundaries for Python workflows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar, cast

from rath.definition.model import EffectClass, NodeKind, RetryPolicy

__all__ = ["router", "step"]

F = TypeVar("F", bound=Callable[..., Any])
_METADATA_ATTR = "__openrath_node_spec__"


@dataclass(frozen=True, slots=True)
class _NodeMetadata:
    kind: NodeKind
    entry: bool
    successors: tuple[str, ...]
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    effects: EffectClass = EffectClass.NON_IDEMPOTENT
    idempotency_key: str | None = None
    timeout_seconds: float | None = None
    checkpoint: bool = True


def _decorate(function: F, metadata: _NodeMetadata) -> F:
    if hasattr(function, _METADATA_ATTR):
        raise ValueError(f"{function.__qualname__} already has OpenRath node metadata")
    if (
        metadata.effects is EffectClass.NON_IDEMPOTENT
        and metadata.retry.max_attempts > 1
        and not metadata.idempotency_key
    ):
        raise ValueError("non-idempotent retries require idempotency_key")
    setattr(function, _METADATA_ATTR, metadata)
    return function


def step(
    *,
    entry: bool = False,
    successors: tuple[str, ...] = (),
    retry: RetryPolicy | None = None,
    effects: EffectClass = EffectClass.NON_IDEMPOTENT,
    idempotency_key: str | None = None,
    timeout_seconds: float | None = None,
    checkpoint: bool = True,
) -> Callable[[F], F]:
    """Mark a method as a checkpointable execution step."""

    def decorator(function: F) -> F:
        return _decorate(
            function,
            _NodeMetadata(
                kind=NodeKind.STEP,
                entry=entry,
                successors=tuple(successors),
                retry=retry or RetryPolicy(),
                effects=effects,
                idempotency_key=idempotency_key,
                timeout_seconds=timeout_seconds,
                checkpoint=checkpoint,
            ),
        )

    return decorator


def router(
    *,
    successors: tuple[str, ...],
    entry: bool = False,
) -> Callable[[F], F]:
    """Mark a pure routing method with an explicit successor allowlist."""
    if not successors:
        raise ValueError("router successors must not be empty")

    def decorator(function: F) -> F:
        return _decorate(
            function,
            _NodeMetadata(
                kind=NodeKind.ROUTER,
                entry=entry,
                successors=tuple(successors),
                effects=EffectClass.NONE,
            ),
        )

    return decorator


def _metadata(function: Callable[..., Any]) -> _NodeMetadata | None:
    return cast(_NodeMetadata | None, getattr(function, _METADATA_ATTR, None))
