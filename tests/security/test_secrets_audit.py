from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from rath.context import RunContext
from rath.security import (
    Action,
    AuditEvent,
    AuditKind,
    InMemoryAuditSink,
    PolicyDecision,
    PolicyEffect,
    ResolvedSecret,
    ResourceRef,
    SecretRef,
    StructuredAuditSink,
)


def test_resolved_secret_never_exposes_value_in_repr_or_str() -> None:
    secret = ResolvedSecret(
        ref=SecretRef(provider="env", key="OPENAI_API_KEY"),
        value="super-secret-value",
    )

    assert "super-secret-value" not in repr(secret)
    assert "super-secret-value" not in str(secret)
    assert secret.reveal() == "super-secret-value"


def test_audit_sink_preserves_security_correlation_without_secret_values() -> None:
    async def exercise() -> None:
        context = RunContext.local(revision_id=uuid4())
        event = AuditEvent.for_policy_decision(
            kind=AuditKind.POLICY_DECISION,
            action=Action("provider.invoke"),
            resource=ResourceRef(kind="provider", id="openai-main"),
            context=context,
            decision=PolicyDecision(
                effect=PolicyEffect.ALLOW,
                reason="local trusted mode",
                policy_id="local",
            ),
            attributes={"secret_ref": "env:OPENAI_API_KEY"},
        )
        sink = InMemoryAuditSink()
        await sink.emit(event)

        assert sink.events == (event,)
        assert event.request_id == context.request_id
        assert event.trace_id == context.trace_context.trace_id
        assert event.tenant_id == "local"

    asyncio.run(exercise())


def test_structured_audit_sink_emits_redacted_correlated_json() -> None:
    async def exercise() -> None:
        context = RunContext.local(revision_id=uuid4())
        event = AuditEvent.for_policy_decision(
            kind=AuditKind.POLICY_DECISION,
            action=Action("provider.invoke"),
            resource=ResourceRef(kind="provider", id="openai-main"),
            context=context,
            decision=PolicyDecision(
                effect=PolicyEffect.ALLOW,
                reason="approved",
                policy_id="release-policy",
            ),
            attributes={
                "authorization": "Bearer super-secret-value",
                "secret_ref": "env:OPENAI_API_KEY",
            },
        )
        lines: list[str] = []
        await StructuredAuditSink(lines.append).emit(event)

        assert len(lines) == 1
        assert "super-secret-value" not in lines[0]
        record = json.loads(lines[0])
        assert record["schema"] == "openrath.security-audit/1"
        assert record["request_id"] == str(context.request_id)
        assert record["trace_id"] == context.trace_context.trace_id
        assert record["action"] == "provider.invoke"
        assert record["attributes"]["authorization"] == "<redacted>"

    asyncio.run(exercise())
