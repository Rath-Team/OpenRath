from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from rath.adapters import (
    AdapterRequestContext,
    MemoryExecutor,
    MemoryNamespace,
    ProviderCapability,
    ProviderExecutor,
    ProviderSpec,
    SandboxExecutor,
    SandboxIsolation,
    SandboxSpec,
    SchemaValidationError,
    ToolExecutor,
    ToolOutputTooLarge,
    ToolSpec,
)
from rath.artifacts import LocalArtifactStore
from rath.context import RunContext
from rath.definition import EffectClass
from rath.security import LocalTrustedPolicy, PolicyConstraints, TrustLevel


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


def test_large_output_can_be_externalized_to_artifact_store(tmp_path) -> None:
    run, adapter = _contexts()
    spec = ToolSpec(
        name="report",
        version="1",
        input_schema={"type": "object"},
        effects=EffectClass.READ_ONLY,
        risk="low",
    )
    result = asyncio.run(
        ToolExecutor(
            LocalTrustedPolicy(),
            artifact_store=LocalArtifactStore(tmp_path / "artifacts"),
        ).execute(
            spec,
            lambda arguments, context: {"data": "x" * 100},
            {},
            adapter_context=adapter,
            run_context=run,
        )
    )

    assert result["artifact_uri"].startswith("artifact://local/")
    assert result["size"] > 32


def test_provider_sandbox_and_memory_share_context_policy_timeout_contract() -> None:
    async def exercise() -> None:
        run, adapter = _contexts()
        policy = LocalTrustedPolicy()
        provider_result = await ProviderExecutor(policy).execute(
            ProviderSpec(
                id="chat",
                kind="openai",
                model="gpt",
                capabilities=frozenset({ProviderCapability.CHAT}),
            ),
            lambda request, spec, context: {"text": "ok"},
            {"messages": []},
            capability=ProviderCapability.CHAT,
            adapter_context=adapter,
            run_context=run,
        )
        sandbox_result = await SandboxExecutor(policy).execute(
            SandboxSpec(
                id="local",
                isolation=SandboxIsolation.TRUSTED_HOST,
                network="deny",
            ),
            lambda operation, payload, spec, context: {"exit_code": 0},
            "command",
            {"argv": ["true"]},
            adapter_context=adapter,
            run_context=run,
        )
        memory_result = await MemoryExecutor(policy).execute(
            lambda operation, namespace, payload, context: {"items": []},
            "search",
            MemoryNamespace(tenant_id="local", trust=TrustLevel.UNTRUSTED),
            {"query": "q"},
            adapter_context=adapter,
            run_context=run,
        )

        assert provider_result == {"text": "ok"}
        assert sandbox_result == {"exit_code": 0}
        assert memory_result == {"items": []}

    asyncio.run(exercise())
