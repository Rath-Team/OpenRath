"""Governed Sandbox v2 execution boundary."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Mapping
from typing import Protocol, cast

from rath.adapters.context import (
    AdapterRequestContext,
    effective_timeout_seconds,
    with_policy_constraints,
)
from rath.adapters.specs import SandboxSpec
from rath.context import RunContext
from rath.security import Action, PolicyEngine, ResourceRef, authorize

__all__ = ["SandboxExecutor", "SandboxHandler"]


class SandboxHandler(Protocol):
    def __call__(
        self,
        operation: str,
        payload: Mapping[str, object],
        spec: SandboxSpec,
        context: AdapterRequestContext,
    ) -> object | Awaitable[object]: ...


class SandboxExecutor:
    def __init__(self, policy: PolicyEngine) -> None:
        self.policy = policy

    async def execute(
        self,
        spec: SandboxSpec,
        handler: SandboxHandler,
        operation: str,
        payload: Mapping[str, object],
        *,
        adapter_context: AdapterRequestContext,
        run_context: RunContext,
        timeout_seconds: float = 60,
    ) -> object:
        if not operation:
            raise ValueError("sandbox operation is required")
        if timeout_seconds <= 0:
            raise ValueError("sandbox timeout must be positive")
        if adapter_context.tenant_id != run_context.security.tenant_id:
            raise PermissionError("adapter and run tenant mismatch")
        decision = await authorize(
            self.policy,
            action=Action("sandbox.execute"),
            resource=ResourceRef(
                kind="sandbox",
                id=spec.id,
                tenant_id=adapter_context.tenant_id,
                attributes={
                    "isolation": spec.isolation.value,
                    "network": spec.network,
                    "operation": operation,
                },
            ),
            context=run_context,
        )
        adapter_context = with_policy_constraints(
            adapter_context,
            decision.constraints,
        )
        timeout = effective_timeout_seconds(
            timeout_seconds,
            adapter_context=adapter_context,
            run_remaining_seconds=run_context.remaining_seconds(),
        )
        started = time.monotonic()
        result = handler(operation, payload, spec, adapter_context)
        if inspect.isawaitable(result):
            return await asyncio.wait_for(
                cast(Awaitable[object], result), timeout=timeout
            )
        if time.monotonic() - started > timeout:
            raise TimeoutError(f"sandbox {spec.id!r} exceeded timeout")
        return result
