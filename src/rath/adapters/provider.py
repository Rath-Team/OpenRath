"""Governed Provider v2 execution boundary."""

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
from rath.adapters.specs import ProviderCapability, ProviderSpec
from rath.context import RunContext
from rath.security import Action, PolicyEngine, ResourceRef, authorize

__all__ = ["ProviderExecutor", "ProviderHandler"]


class ProviderHandler(Protocol):
    def __call__(
        self,
        request: Mapping[str, object],
        spec: ProviderSpec,
        context: AdapterRequestContext,
    ) -> object | Awaitable[object]: ...


class ProviderExecutor:
    def __init__(self, policy: PolicyEngine) -> None:
        self.policy = policy
        self._semaphores: dict[str, asyncio.Semaphore] = {}

    async def execute(
        self,
        spec: ProviderSpec,
        handler: ProviderHandler,
        request: Mapping[str, object],
        *,
        capability: ProviderCapability,
        adapter_context: AdapterRequestContext,
        run_context: RunContext,
    ) -> object:
        if capability not in spec.capabilities:
            raise ValueError(
                f"provider {spec.id!r} does not declare {capability.value!r}"
            )
        if adapter_context.tenant_id != run_context.security.tenant_id:
            raise PermissionError("adapter and run tenant mismatch")
        decision = await authorize(
            self.policy,
            action=Action("provider.invoke"),
            resource=ResourceRef(
                kind="provider",
                id=spec.id,
                tenant_id=adapter_context.tenant_id,
                attributes={
                    "kind": spec.kind,
                    "model": spec.model,
                    "capability": capability.value,
                },
            ),
            context=run_context,
        )
        adapter_context = with_policy_constraints(
            adapter_context,
            decision.constraints,
        )
        semaphore = self._semaphores.setdefault(
            spec.id, asyncio.Semaphore(spec.max_concurrency)
        )
        timeout = effective_timeout_seconds(
            spec.total_timeout_seconds,
            adapter_context=adapter_context,
            run_remaining_seconds=run_context.remaining_seconds(),
        )
        async with semaphore:
            started = time.monotonic()
            result = handler(request, spec, adapter_context)
            if inspect.isawaitable(result):
                return await asyncio.wait_for(
                    cast(Awaitable[object], result),
                    timeout=timeout,
                )
            if time.monotonic() - started > timeout:
                raise TimeoutError(f"provider {spec.id!r} exceeded timeout")
            return result
