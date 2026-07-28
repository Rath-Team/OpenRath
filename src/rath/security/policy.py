"""Fail-closed authorization contracts and reference policies."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from rath._json import JSONValue, freeze_mapping
from rath.errors import ErrorCode, RathError

if TYPE_CHECKING:
    from rath.context import RunContext

__all__ = [
    "Action",
    "ApprovalRequiredError",
    "AuthorizationError",
    "DenyAllPolicy",
    "LocalTrustedPolicy",
    "PolicyConstraints",
    "PolicyDecision",
    "PolicyEffect",
    "PolicyEngine",
    "PolicyEvaluationError",
    "ResourceRef",
    "authorize",
]


def _required(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


@dataclass(frozen=True, slots=True)
class Action:
    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required(self.name, field_name="action"))

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True, slots=True)
class ResourceRef:
    kind: str
    id: str
    tenant_id: str | None = None
    attributes: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "kind",
            _required(self.kind, field_name="resource.kind"),
        )
        object.__setattr__(
            self,
            "id",
            _required(self.id, field_name="resource.id"),
        )
        object.__setattr__(
            self,
            "attributes",
            freeze_mapping(self.attributes, field="resource.attributes"),
        )


@dataclass(frozen=True, slots=True)
class PolicyConstraints:
    timeout_seconds: float | None = None
    max_output_bytes: int | None = None
    allowed_network_hosts: frozenset[str] = field(default_factory=frozenset)
    filesystem_root: str | None = None
    read_only: bool = False
    redactions: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if self.max_output_bytes is not None and self.max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be greater than zero")
        object.__setattr__(
            self,
            "allowed_network_hosts",
            frozenset(host.lower() for host in self.allowed_network_hosts),
        )
        object.__setattr__(self, "redactions", frozenset(self.redactions))


class PolicyEffect(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    ALLOW_WITH_CONSTRAINTS = "allow_with_constraints"


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    effect: PolicyEffect
    reason: str
    policy_id: str
    constraints: PolicyConstraints = field(default_factory=PolicyConstraints)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reason",
            _required(self.reason, field_name="policy reason"),
        )
        object.__setattr__(
            self,
            "policy_id",
            _required(self.policy_id, field_name="policy_id"),
        )


@runtime_checkable
class PolicyEngine(Protocol):
    async def evaluate(
        self,
        action: Action,
        resource: ResourceRef,
        context: RunContext,
    ) -> PolicyDecision: ...


class AuthorizationError(RathError):
    def __init__(self, decision: PolicyDecision) -> None:
        super().__init__(
            ErrorCode.FORBIDDEN,
            decision.reason,
            retryable=False,
            details={
                "effect": decision.effect.value,
                "policy_id": decision.policy_id,
            },
        )
        self.decision = decision


class ApprovalRequiredError(RathError):
    def __init__(self, decision: PolicyDecision) -> None:
        super().__init__(
            ErrorCode.APPROVAL_REQUIRED,
            decision.reason,
            retryable=False,
            details={"policy_id": decision.policy_id},
        )
        self.decision = decision


class PolicyEvaluationError(RathError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.POLICY_ERROR,
            "policy evaluation failed closed",
            retryable=False,
        )


class DenyAllPolicy:
    """Safe default for service and untrusted deployment profiles."""

    async def evaluate(
        self,
        action: Action,
        resource: ResourceRef,
        context: RunContext,
    ) -> PolicyDecision:
        return PolicyDecision(
            effect=PolicyEffect.DENY,
            reason="no policy grant allows this action",
            policy_id="deny-all",
        )


class LocalTrustedPolicy:
    """Explicit opt-in policy for the embedded trusted-process profile."""

    async def evaluate(
        self,
        action: Action,
        resource: ResourceRef,
        context: RunContext,
    ) -> PolicyDecision:
        allowed = context.security.tenant_id == "local" and context.security.has_grant(
            "trusted_host"
        )
        return PolicyDecision(
            effect=PolicyEffect.ALLOW if allowed else PolicyEffect.DENY,
            reason=(
                "explicit embedded trusted-host context"
                if allowed
                else "trusted-host policy is restricted to embedded local context"
            ),
            policy_id="local-trusted",
        )


async def authorize(
    engine: PolicyEngine,
    *,
    action: Action,
    resource: ResourceRef,
    context: RunContext,
) -> PolicyDecision:
    """Evaluate a policy and turn non-allow effects into stable exceptions."""
    context.ensure_active()
    try:
        decision = await engine.evaluate(action, resource, context)
    except RathError:
        raise
    except Exception as exc:
        raise PolicyEvaluationError() from exc
    if decision.effect is PolicyEffect.DENY:
        raise AuthorizationError(decision)
    if decision.effect is PolicyEffect.REQUIRE_APPROVAL:
        raise ApprovalRequiredError(decision)
    return decision
