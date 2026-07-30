from __future__ import annotations

from uuid import uuid4

import pytest

from rath.definition import (
    DefinitionError,
    EffectClass,
    NodeKind,
    RetryPolicy,
    WorkflowCompiler,
    router,
    step,
)
from rath.flow import Workflow
from rath.session import Session


class _Research(Workflow):
    @step(
        entry=True,
        successors=("route",),
        retry=RetryPolicy(max_attempts=3),
        effects=EffectClass.READ_ONLY,
    )
    async def search(self, state, context):  # type: ignore[no-untyped-def]
        return state

    @router(successors=("write", "review"))
    def route(self, state):  # type: ignore[no-untyped-def]
        return "write"

    @step()
    def review(self, state, context):  # type: ignore[no-untyped-def]
        return state

    @step()
    def write(self, state, context):  # type: ignore[no-untyped-def]
        return state

    def forward(self, session: Session) -> Session:
        return session


def test_compiler_produces_deterministic_immutable_plan() -> None:
    revision_id = uuid4()
    first = WorkflowCompiler().compile(_Research(), revision_id=revision_id)
    second = WorkflowCompiler().compile(_Research(), revision_id=revision_id)

    assert first.id == second.id
    assert first.definition_hash == second.definition_hash
    assert first.revision_id == revision_id
    assert tuple(node.id for node in first.nodes) == (
        "review",
        "route",
        "search",
        "write",
    )
    route_node = next(node for node in first.nodes if node.id == "route")
    assert route_node.kind is NodeKind.ROUTER
    assert route_node.successors == ("write", "review")
    search_node = next(node for node in first.nodes if node.id == "search")
    assert search_node.retry.max_attempts == 3
    assert search_node.effects is EffectClass.READ_ONLY
    assert first.durable is True


def test_workflow_compile_plan_is_public_convenience_api() -> None:
    plan = _Research().compile_plan(revision_id=uuid4())
    assert plan.definition.entrypoint == "search"
    assert plan.definition.version == "1"


def test_unknown_router_successor_fails_compile() -> None:
    class _Broken(Workflow):
        @router(entry=True, successors=("missing",))
        def route(self, state):  # type: ignore[no-untyped-def]
            return "missing"

        def forward(self, session: Session) -> Session:
            return session

    with pytest.raises(DefinitionError, match="unknown successor"):
        WorkflowCompiler().compile(_Broken(), revision_id=uuid4())


def test_multiple_entry_steps_fail_compile() -> None:
    class _Broken(Workflow):
        @step(entry=True)
        def one(self, state, context):  # type: ignore[no-untyped-def]
            return state

        @step(entry=True)
        def two(self, state, context):  # type: ignore[no-untyped-def]
            return state

        def forward(self, session: Session) -> Session:
            return session

    with pytest.raises(DefinitionError, match="exactly one entrypoint"):
        WorkflowCompiler().compile(_Broken(), revision_id=uuid4())


def test_legacy_workflow_compiles_as_opaque_non_durable_plan() -> None:
    class _Legacy(Workflow):
        def forward(self, session: Session) -> Session:
            return session

    plan = WorkflowCompiler().compile(_Legacy(), revision_id=uuid4())

    assert plan.durable is False
    assert plan.nodes[0].kind is NodeKind.OPAQUE
    assert any("checkpoint" in issue for issue in plan.compatibility_issues)


def test_step_metadata_rejects_unsafe_retry_contract() -> None:
    with pytest.raises(ValueError, match="idempotency"):

        @step(
            retry=RetryPolicy(max_attempts=2),
            effects=EffectClass.NON_IDEMPOTENT,
        )
        def unsafe(state, context):  # type: ignore[no-untyped-def]
            return state


def test_production_durable_rejects_sync_step_timeout() -> None:
    class _TimedSync(Workflow):
        @step(entry=True, timeout_seconds=0.1)
        def run(self, state, context):  # type: ignore[no-untyped-def]
            return state

        def forward(self, session: Session) -> Session:
            return session

    with pytest.raises(
        DefinitionError,
        match="synchronous durable steps cannot guarantee preemptive timeout",
    ):
        WorkflowCompiler().compile(
            _TimedSync(),
            revision_id=uuid4(),
            production_durable=True,
        )
