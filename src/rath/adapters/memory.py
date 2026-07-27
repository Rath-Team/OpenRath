"""Governed tenant-scoped Memory v2 execution boundary."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Mapping
from typing import Literal, Protocol, cast

from rath.adapters.context import AdapterRequestContext
from rath.adapters.specs import MemoryNamespace
from rath.context import RunContext
from rath.security import Action, PolicyEngine, ResourceRef, authorize

__all__ = ["MemoryExecutor", "MemoryHandler"]


class MemoryHandler(Protocol):
    def __call__(
        self,
        operation: Literal["put", "search", "delete"],
        namespace: MemoryNamespace,
        payload: Mapping[str, object],
        context: AdapterRequestContext,
    ) -> object | Awaitable[object]: ...


class MemoryExecutor:
    def __init__(self, policy: PolicyEngine) -> None:
        self.policy = policy

    async def execute(
        self,
        handler: MemoryHandler,
        operation: Literal["put", "search", "delete"],
        namespace: MemoryNamespace,
        payload: Mapping[str, object],
        *,
        adapter_context: AdapterRequestContext,
        run_context: RunContext,
        timeout_seconds: float = 30,
    ) -> object:
        if timeout_seconds <= 0:
            raise ValueError("memory timeout must be positive")
        tenant_id = run_context.security.tenant_id
        if namespace.tenant_id != tenant_id or adapter_context.tenant_id != tenant_id:
            raise PermissionError("memory namespace tenant mismatch")
        await authorize(
            self.policy,
            action=Action(f"memory.{operation}"),
            resource=ResourceRef(
                kind="memory_namespace",
                id=":".join(
                    item
                    for item in (
                        namespace.tenant_id,
                        namespace.user_id,
                        namespace.agent_id,
                        namespace.session_id,
                    )
                    if item is not None
                ),
                tenant_id=tenant_id,
                attributes={"trust": namespace.trust.value},
            ),
            context=run_context,
        )
        result = handler(operation, namespace, payload, adapter_context)
        if inspect.isawaitable(result):
            return await asyncio.wait_for(
                cast(Awaitable[object], result), timeout=timeout_seconds
            )
        return result
