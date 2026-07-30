"""Policy-governed Tool v2 execution boundary."""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from typing import Protocol, cast
from uuid import UUID

from rath.adapters.context import (
    AdapterRequestContext,
    effective_timeout_seconds,
    with_policy_constraints,
)
from rath.adapters.schema import validate_json
from rath.adapters.specs import ToolSpec
from rath.artifacts import ArtifactStore
from rath.context import RunContext
from rath.definition import EffectClass
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

__all__ = [
    "ApprovalGrant",
    "ApprovalValidator",
    "ToolExecutor",
    "ToolHandler",
    "ToolOutputTooLarge",
]


class ToolOutputTooLarge(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ApprovalGrant:
    decision_id: UUID
    run_id: UUID
    node_id: str
    tenant_id: str
    tool_id: str
    arguments_digest: str
    actor_id: str


class ApprovalValidator(Protocol):
    def __call__(self, grant: ApprovalGrant) -> bool | Awaitable[bool]: ...


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
        artifact_store: ArtifactStore | None = None,
        approval_validator: ApprovalValidator | None = None,
    ) -> None:
        self.policy = policy
        self.effect_ledger = effect_ledger
        self.artifact_store = artifact_store
        self.approval_validator = approval_validator

    async def execute(
        self,
        spec: ToolSpec,
        handler: ToolHandler,
        arguments: Mapping[str, object],
        *,
        adapter_context: AdapterRequestContext,
        run_context: RunContext,
        approval: ApprovalGrant | None = None,
        run_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> object:
        validate_json(arguments, spec.input_schema)
        if adapter_context.tenant_id != run_context.security.tenant_id:
            raise PermissionError("adapter and run tenant mismatch")
        digest = arguments_digest(arguments)
        approval_valid = False
        if approval is not None:
            if (
                approval.run_id != adapter_context.run_id
                or approval.node_id != adapter_context.node_id
                or approval.tenant_id != adapter_context.tenant_id
                or approval.tool_id != f"{spec.name}@{spec.version}"
                or approval.arguments_digest != digest
            ):
                raise PermissionError("approval grant does not match tool invocation")
            if self.approval_validator is None:
                raise PermissionError("approval grant cannot be verified")
            validated = self.approval_validator(approval)
            approval_valid = (
                await validated if inspect.isawaitable(validated) else bool(validated)
            )
            if not approval_valid:
                raise PermissionError("approval grant is not valid")
        try:
            decision = await authorize(
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
        except ApprovalRequiredError as exc:
            if not approval_valid:
                raise
            decision = exc.decision
        adapter_context = with_policy_constraints(
            adapter_context,
            decision.constraints,
        )
        if spec.requires_approval and not approval_valid:
            raise ApprovalRequiredError(
                PolicyDecision(
                    effect=PolicyEffect.REQUIRE_APPROVAL,
                    reason=f"tool {spec.name} requires approval",
                    policy_id="tool-spec",
                )
            )
        invocation = None
        ledger = self.effect_ledger
        effective_idempotency_key = (
            idempotency_key
            if idempotency_key is not None
            else adapter_context.idempotency_key
        )
        if ledger is not None:
            if run_id is None:
                raise ValueError("run_id is required when effect ledger is enabled")
            invocation = ledger.prepare(
                run_id=run_id,
                tool_name=f"{spec.name}@{spec.version}",
                effect_class=spec.effects,
                arguments_digest=digest,
                idempotency_key=effective_idempotency_key,
                node_id=adapter_context.node_id,
                checkpoint_sequence=adapter_context.checkpoint_sequence,
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
        effective_timeout = effective_timeout_seconds(
            spec.timeout_seconds,
            adapter_context=adapter_context,
            run_remaining_seconds=run_context.remaining_seconds(),
        )
        started = time.monotonic()
        try:
            result = handler(arguments, adapter_context)
            if inspect.isawaitable(result):
                result = await asyncio.wait_for(
                    cast(Awaitable[object], result),
                    timeout=effective_timeout,
                )
            elif time.monotonic() - started > effective_timeout:
                raise TimeoutError(f"tool {spec.name}@{spec.version} exceeded timeout")
        except BaseException as exc:
            if (
                invocation is not None
                and ledger is not None
                and spec.effects is not EffectClass.NON_IDEMPOTENT
                and not isinstance(exc, (TimeoutError, asyncio.TimeoutError))
            ):
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
            if self.artifact_store is not None:
                artifact = self.artifact_store.put(
                    adapter_context.tenant_id,
                    encoded,
                    media_type="application/json",
                    metadata={
                        "tool": f"{spec.name}@{spec.version}",
                        "run_id": str(run_id) if run_id is not None else None,
                    },
                )
                reference = {
                    "artifact_uri": artifact.uri,
                    "digest": artifact.digest,
                    "size": artifact.size,
                    "media_type": artifact.media_type,
                }
                if invocation is not None and ledger is not None:
                    ledger.complete(invocation.id, reference)
                return reference
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
