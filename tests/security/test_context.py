from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from rath.context import DeadlineExceededError, RunContext, TraceContext
from rath.security import Principal, PrincipalKind, SecurityContext


def test_security_context_is_deeply_immutable() -> None:
    claims = {"roles": ["developer"], "profile": {"region": "cn"}}
    principal = Principal(
        id="user-1",
        kind=PrincipalKind.USER,
        claims=claims,
    )
    context = SecurityContext(
        principal=principal,
        tenant_id="tenant-1",
        project_id="project-1",
        grants={"tool.search", "memory.read"},
    )

    claims["roles"].append("admin")
    claims["profile"]["region"] = "other"  # type: ignore[index]

    assert principal.claims["roles"] == ("developer",)
    assert principal.claims["profile"]["region"] == "cn"  # type: ignore[index]
    assert context.grants == frozenset({"tool.search", "memory.read"})
    with pytest.raises(TypeError):
        principal.claims["new"] = True  # type: ignore[index]


def test_local_context_is_explicit_and_not_anonymous() -> None:
    context = SecurityContext.local()

    assert context.tenant_id == "local"
    assert context.principal.id == "local-process"
    assert context.principal.kind is PrincipalKind.SYSTEM
    assert "trusted_host" in context.grants


def test_trace_context_uses_w3c_sized_hex_identifiers() -> None:
    trace = TraceContext.new()

    assert len(trace.trace_id) == 32
    assert len(trace.span_id) == 16
    int(trace.trace_id, 16)
    int(trace.span_id, 16)


def test_run_context_rejects_naive_deadline() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        RunContext(
            security=SecurityContext.local(),
            revision_id=uuid4(),
            deadline=datetime.now(),
        )


def test_run_context_deadline_check_uses_stable_error_code() -> None:
    context = RunContext(
        security=SecurityContext.local(),
        revision_id=uuid4(),
        deadline=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    with pytest.raises(DeadlineExceededError) as raised:
        context.ensure_active()

    assert raised.value.code.value == "runtime.deadline_exceeded"
    assert isinstance(context.request_id, UUID)

