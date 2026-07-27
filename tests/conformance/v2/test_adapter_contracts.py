from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from rath.adapters import (
    AdapterRequestContext,
    SchemaValidationError,
    ToolExecutor,
    ToolOutputTooLarge,
    ToolSpec,
)
from rath.context import RunContext
from rath.definition import EffectClass
from rath.security import LocalTrustedPolicy, PolicyConstraints


def _contexts():  # type: ignore[no-untyped-def]
    run = RunContext.local(revision_id=uuid4())
    adapter = AdapterRequestContext(
        run_id=uuid4(),
        node_id="tool",
        tenant_id="local",
        deadline=None,
        trace_context=run.trace_context,
        idempotency_key="key",
        policy_constraints=PolicyConstraints(max_output_bytes=32),
    )
    return run, adapter


def test_tool_schema_is_validated_before_handler() -> None:
    called = False

    def handler(arguments, context):  # type: ignore[no-untyped-def]
        nonlocal called
        called = True
        return {"ok": True}

    run, adapter = _contexts()
    spec = ToolSpec(
        name="search",
        version="1",
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
            "additionalProperties": False,
        },
        effects=EffectClass.READ_ONLY,
        risk="low",
    )
    with pytest.raises(SchemaValidationError):
        asyncio.run(
            ToolExecutor(LocalTrustedPolicy()).execute(
                spec,
                handler,
                {"unknown": True},
                adapter_context=adapter,
                run_context=run,
            )
        )
    assert called is False


def test_tool_output_budget_is_enforced() -> None:
    run, adapter = _contexts()
    spec = ToolSpec(
        name="large",
        version="1",
        input_schema={"type": "object"},
        effects=EffectClass.READ_ONLY,
        risk="low",
    )
    with pytest.raises(ToolOutputTooLarge):
        asyncio.run(
            ToolExecutor(LocalTrustedPolicy()).execute(
                spec,
                lambda arguments, context: {"data": "x" * 100},
                {},
                adapter_context=adapter,
                run_context=run,
            )
        )

