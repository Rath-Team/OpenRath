"""Single governed execution boundary used by durable runtime workers."""

from __future__ import annotations

import asyncio
import inspect
import time
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Coroutine, Protocol, cast

from rath.definition import NodeKind, NodeSpec
from rath.runtime.effects import EffectLedger
from rath.runtime.models import Run
from rath.runtime.store import RunStore

if TYPE_CHECKING:
    from rath.adapters import (
        MemoryExecutor,
        ProviderExecutor,
        SandboxExecutor,
        ToolExecutor,
    )
    from rath.runtime.local import StepContext
    from rath.security import AuditSink, PolicyEngine

__all__ = [
    "ExecutionServices",
    "PythonStepExecutor",
    "StepSuspended",
    "StepExecutor",
]


@dataclass(frozen=True, slots=True)
class ExecutionServices:
    """Governed capabilities made available to a workflow step."""

    policy: PolicyEngine
    tools: ToolExecutor
    providers: ProviderExecutor
    sandboxes: SandboxExecutor
    memory: MemoryExecutor
    effects: EffectLedger
    audit: AuditSink


class StepExecutor(Protocol):
    """Execute one compiled node through the durable worker boundary."""

    def execute(
        self,
        *,
        handler: object,
        state: dict[str, object],
        context: StepContext,
        node: NodeSpec,
        run: Run,
    ) -> object: ...


class StepSuspended(RuntimeError):
    """Internal control flow indicating a durable interrupt boundary."""


class PythonStepExecutor:
    """Reference in-process executor for embedded and async durable steps."""

    def __init__(self, store: RunStore) -> None:
        self.store = store

    def execute(
        self,
        *,
        handler: object,
        state: dict[str, object],
        context: StepContext,
        node: NodeSpec,
        run: Run,
    ) -> object:
        last_error: BaseException | None = None
        for attempt in range(1, node.retry.max_attempts + 1):
            try:
                callable_handler = cast(Any, handler)
                if node.is_async:
                    value = (
                        callable_handler(state, context)
                        if node.kind is not NodeKind.ROUTER
                        else callable_handler(state)
                    )
                    if not inspect.isawaitable(value):
                        raise TypeError(
                            f"async step {node.id!r} did not return an awaitable"
                        )
                    from rath._async.runtime import runtime as async_runtime

                    coroutine = cast(Coroutine[Any, Any, object], value)
                    if node.timeout_seconds is not None:
                        coroutine = cast(
                            Coroutine[Any, Any, object],
                            asyncio.wait_for(coroutine, node.timeout_seconds),
                        )
                    return async_runtime().run(coroutine)

                arguments = (
                    (state,) if node.kind is NodeKind.ROUTER else (state, context)
                )
                if node.timeout_seconds is None:
                    return callable_handler(*arguments)
                started = time.monotonic()
                result = callable_handler(*arguments)
                if time.monotonic() - started > node.timeout_seconds:
                    raise FutureTimeout(
                        f"sync step {node.id!r} exceeded timeout; "
                        "the handler was allowed to stop before terminalization"
                    )
                return result
            except StepSuspended:
                raise
            except BaseException as exc:
                last_error = exc
                self.store.append_run_event(
                    run.id,
                    "run.step.attempt.failed",
                    {
                        "node_id": node.id,
                        "attempt": attempt,
                        "error_type": type(exc).__name__,
                    },
                )
                if attempt >= node.retry.max_attempts:
                    raise
                delay = min(
                    node.retry.max_seconds,
                    node.retry.base_seconds * (2 ** (attempt - 1)),
                )
                time.sleep(delay)
        assert last_error is not None
        raise last_error
