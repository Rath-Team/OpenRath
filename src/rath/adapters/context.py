"""Uniform request context propagated to every external adapter."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from uuid import UUID

from rath.context import TraceContext
from rath.security import PolicyConstraints

__all__ = [
    "AdapterRequestContext",
    "effective_timeout_seconds",
    "merge_policy_constraints",
    "with_policy_constraints",
]


@dataclass(frozen=True, slots=True)
class AdapterRequestContext:
    run_id: UUID
    node_id: str
    tenant_id: str
    deadline: datetime | None
    trace_context: TraceContext
    idempotency_key: str | None
    policy_constraints: PolicyConstraints
    checkpoint_sequence: int | None = None

    def __post_init__(self) -> None:
        if not self.node_id.strip():
            raise ValueError("adapter node_id must not be empty")
        if not self.tenant_id.strip():
            raise ValueError("adapter tenant_id must not be empty")
        if self.deadline is not None and self.deadline.tzinfo is None:
            raise ValueError("adapter deadline must be timezone-aware")
        if self.checkpoint_sequence is not None and self.checkpoint_sequence < 1:
            raise ValueError("checkpoint_sequence must be positive")


def effective_timeout_seconds(
    requested: float,
    *,
    adapter_context: AdapterRequestContext,
    run_remaining_seconds: float | None,
) -> float:
    """Resolve the strictest positive timeout from spec, policy and deadlines."""

    candidates = [requested]
    policy_timeout = adapter_context.policy_constraints.timeout_seconds
    if policy_timeout is not None:
        candidates.append(policy_timeout)
    if run_remaining_seconds is not None:
        candidates.append(run_remaining_seconds)
    if adapter_context.deadline is not None:
        candidates.append(
            max(
                0.0,
                (adapter_context.deadline - datetime.now(timezone.utc)).total_seconds(),
            )
        )
    return min(candidates)


def merge_policy_constraints(
    declared: PolicyConstraints,
    decided: PolicyConstraints,
) -> PolicyConstraints:
    """Combine caller and policy limits without weakening either side."""

    timeouts = [
        value
        for value in (declared.timeout_seconds, decided.timeout_seconds)
        if value is not None
    ]
    output_limits = [
        value
        for value in (declared.max_output_bytes, decided.max_output_bytes)
        if value is not None
    ]
    if declared.allowed_network_hosts and decided.allowed_network_hosts:
        allowed_hosts = declared.allowed_network_hosts & decided.allowed_network_hosts
    else:
        allowed_hosts = declared.allowed_network_hosts or decided.allowed_network_hosts
    return PolicyConstraints(
        timeout_seconds=min(timeouts) if timeouts else None,
        max_output_bytes=min(output_limits) if output_limits else None,
        allowed_network_hosts=allowed_hosts,
        filesystem_root=decided.filesystem_root or declared.filesystem_root,
        read_only=declared.read_only or decided.read_only,
        redactions=declared.redactions | decided.redactions,
    )


def with_policy_constraints(
    context: AdapterRequestContext,
    constraints: PolicyConstraints,
) -> AdapterRequestContext:
    """Return the adapter context carrying the evaluated policy constraints."""

    return replace(
        context,
        policy_constraints=merge_policy_constraints(
            context.policy_constraints,
            constraints,
        ),
    )
