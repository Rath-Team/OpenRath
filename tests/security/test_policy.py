from __future__ import annotations

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest

from rath.context import RunContext
from rath.security import (
    Action,
    ApprovalRequiredError,
    AuthorizationError,
    DenyAllPolicy,
    LocalTrustedPolicy,
    PolicyConstraints,
    PolicyDecision,
    PolicyEffect,
    ResourceRef,
    authorize,
)


def _context() -> RunContext:
    return RunContext.local(revision_id=uuid4())


def test_deny_all_policy_fails_closed() -> None:
    async def exercise() -> None:
        with pytest.raises(AuthorizationError) as raised:
            await authorize(
                DenyAllPolicy(),
                action=Action("tool.execute"),
                resource=ResourceRef(kind="tool", id="search"),
                context=_context(),
            )
        assert raised.value.code.value == "security.forbidden"

    asyncio.run(exercise())


def test_local_trusted_policy_only_allows_explicit_local_context() -> None:
    async def exercise() -> None:
        decision = await authorize(
            LocalTrustedPolicy(),
            action=Action("sandbox.execute"),
            resource=ResourceRef(kind="sandbox", id="local"),
            context=_context(),
        )
        assert decision.effect is PolicyEffect.ALLOW

        remote_context = replace(
            _context(),
            security=replace(_context().security, tenant_id="tenant-1"),
        )
        with pytest.raises(AuthorizationError):
            await authorize(
                LocalTrustedPolicy(),
                action=Action("sandbox.execute"),
                resource=ResourceRef(kind="sandbox", id="local"),
                context=remote_context,
            )

    asyncio.run(exercise())


def test_approval_decision_is_not_misreported_as_denial() -> None:
    class ApprovalPolicy:
        async def evaluate(
            self,
            action: Action,
            resource: ResourceRef,
            context: RunContext,
        ) -> PolicyDecision:
            return PolicyDecision(
                effect=PolicyEffect.REQUIRE_APPROVAL,
                reason="non-idempotent tool",
                policy_id="test",
            )

    async def exercise() -> None:
        with pytest.raises(ApprovalRequiredError) as raised:
            await authorize(
                ApprovalPolicy(),
                action=Action("tool.execute"),
                resource=ResourceRef(kind="tool", id="email.send"),
                context=_context(),
            )
        assert raised.value.code.value == "security.approval_required"

    asyncio.run(exercise())


def test_policy_constraints_validate_resource_budgets() -> None:
    with pytest.raises(ValueError, match="max_output_bytes"):
        PolicyConstraints(max_output_bytes=0)
    with pytest.raises(ValueError, match="timeout_seconds"):
        PolicyConstraints(timeout_seconds=-1)
