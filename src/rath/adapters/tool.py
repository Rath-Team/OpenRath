"""Policy-governed Tool v2 execution boundary."""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Mapping
from typing import Protocol, cast
from uuid import UUID

from rath.adapters.context import AdapterRequestContext
from rath.adapters.schema import validate_json
from rath.adapters.specs import ToolSpec
from rath.context import RunContext
from rath.runtime.effects import (
    EffectLedger,
    InvocationStatus,
    arguments_digest,
)
from rath.security import (
    Action,
    ApprovalRequiredError,
    PolicyDecision,
    PolicyEffect,
    PolicyEngine,
    ResourceRef,
    authorize,
)

__all__ = ["ToolExecutor", "ToolHandler", "ToolOutputTooLarge"]


class ToolOutputTooLarge(RuntimeError):
    pass


class ToolHandler(Protocol):
    def __call__(
        self,
        arguments: Mapping[str, object],
        context: AdapterRequestContext,
    ) -> object | Awaitable[object]: ...


class ToolExecutor:
    def __init__(
        self,
        policy: PolicyEngine,
        *,
        effect_ledger: EffectLedger | None = None,
    ) -> None:
        self.policy = policy
        self.effect_ledger = effect_ledger

    async def execute(
        self,
        spec: ToolSpec,
        handler: ToolHandler,
        arguments: Mapping[str, object],
        *,
        adapter_context: AdapterRequestContext,
        run_context: RunContext,
        approved: bool = False,
        run_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> object:
        validate_json(arguments, spec.input_schema)
        try:
            await authorize(
                self.policy,
                action=Action("tool.execute"),
                resource=ResourceRef(
                    kind="tool",
                    id=f"{spec.name}@{spec.version}",
                    tenant_id=adapter_context.tenant_id,
                    attributes={"risk": spec.risk, "effects": spec.effects.value},
                ),
                context=run_context,
            )
        except ApprovalRequiredError:
            if not approved:
                raise
        if spec.requires_approval and not approved:
            raise ApprovalRequiredError(
                PolicyDecision(
                    effect=PolicyEffect.REQUIRE_APPROVAL,
                    reason=f"tool {spec.name} requires approval",
                    policy_id="tool-spec",
                )
            )
        invocation = None
        ledger = self.effect_ledger
        if ledger is not None:
            if run_id is None:
                raise ValueError("run_id is required when effect ledger is enabled")
            invocation = ledger.prepare(
                run_id=run_id,
                tool_name=f"{spec.name}@{spec.version}",
                effect_class=spec.effects,
                arguments_digest=arguments_digest(arguments),
                idempotency_key=idempotency_key,
            )
            if invocation.status is InvocationStatus.SUCCEEDED:
                return invocation.result
            if invocation.status in {
                InvocationStatus.AMBIGUOUS,
                InvocationStatus.DISPATCHED,
            }:
                raise RuntimeError(
                    "tool invocation outcome is ambiguous and requires reconciliation"
                )
            invocation = ledger.mark_dispatched(invocation.id)
        try:
            result = handler(arguments, adapter_context)
            if inspect.isawaitable(result):
                result = await cast(Awaitable[object], result)
        except BaseException as exc:
            if invocation is not None and ledger is not None:
                ledger.fail(invocation.id, f"{type(exc).__name__}: {exc}")
            raise
        if spec.output_schema is not None:
            validate_json(result, spec.output_schema)
        encoded = json.dumps(result, ensure_ascii=False, default=str).encode("utf-8")
        limit = min(
            spec.max_output_bytes,
            adapter_context.policy_constraints.max_output_bytes
            or spec.max_output_bytes,
        )
        if len(encoded) > limit:
            if invocation is not None and ledger is not None:
                ledger.fail(
                    invocation.id,
                    f"tool output exceeded {limit} bytes",
                )
            raise ToolOutputTooLarge(
                f"tool output is {len(encoded)} bytes; maximum is {limit}"
            )
        if invocation is not None and ledger is not None:
            ledger.complete(invocation.id, result)
        return result
