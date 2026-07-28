from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from rath.context import RunContext
from rath.definition import EffectClass, RetryPolicy, router, step
from rath.flow import Workflow
from rath.runtime import (
    ApprovalDecision,
    ApprovalDecisionKind,
    InterruptKind,
    LocalRuntime,
    RunStatus,
    SQLiteRunStore,
)
from rath.security import Principal, PrincipalKind, SecurityContext
from rath.session import Session


class _Workflow(Workflow):
    @step(entry=True, successors=("route",), effects=EffectClass.READ_ONLY)
    async def start(self, state, context):  # type: ignore[no-untyped-def]
        return {**state, "count": state.get("count", 0) + 1}

    @router(successors=("finish", "review"))
    def route(self, state):  # type: ignore[no-untyped-def]
        return "finish" if state["count"] == 1 else "review"

    @step(effects=EffectClass.READ_ONLY)
    def finish(self, state, context):  # type: ignore[no-untyped-def]
        return {**state, "result": "done"}

    @step(effects=EffectClass.READ_ONLY)
    def review(self, state, context):  # type: ignore[no-untyped-def]
        return state

    def forward(self, session: Session) -> Session:
        return session


def test_local_runtime_executes_and_checkpoints_every_step(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "runtime.db")
    runtime = LocalRuntime(store)
    context = RunContext.local(revision_id=uuid4())
    submitted = runtime.submit(
        _Workflow(),
        session_id=uuid4(),
        context=context,
        state={"count": 0},
        idempotency_key="request-1",
    )

    completed = runtime.work_once(worker_id="worker-1")

    assert completed is not None
    assert completed.id == submitted.id
    assert completed.status is RunStatus.SUCCEEDED
    assert completed.state["result"] == "done"
    checkpoints = store.list_checkpoints(completed.id)
    assert [checkpoint.sequence for checkpoint in checkpoints] == [1, 2, 3]
    assert checkpoints[-1].next_nodes == ()


def test_runtime_resumes_from_committed_checkpoint_after_lease_expiry(
    tmp_path: Path,
) -> None:
    store = SQLiteRunStore(tmp_path / "runtime.db")
    runtime = LocalRuntime(store)
    context = RunContext.local(revision_id=uuid4())
    submitted = runtime.submit(
        _Workflow(),
        session_id=uuid4(),
        context=context,
        state={"count": 0},
    )
    partial = runtime.work_once(worker_id="worker-1", max_steps=1, lease_seconds=1)
    assert partial is not None
    assert partial.status is RunStatus.RUNNING
    assert partial.next_nodes == ("route",)

    future = datetime.now(timezone.utc) + timedelta(seconds=2)
    assert store.requeue_expired_leases(now=future) == (submitted.id,)
    resumed = runtime.work_once(worker_id="worker-2", now=future)

    assert resumed is not None
    assert resumed.status is RunStatus.SUCCEEDED
    assert resumed.state["count"] == 1
    assert len(store.list_checkpoints(resumed.id)) == 3


def test_runtime_marks_step_exception_failed(tmp_path: Path) -> None:
    class _Broken(Workflow):
        @step(entry=True, effects=EffectClass.READ_ONLY)
        def broken(self, state, context):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

        def forward(self, session: Session) -> Session:
            return session

    store = SQLiteRunStore(tmp_path / "runtime.db")
    runtime = LocalRuntime(store)
    runtime.submit(
        _Broken(),
        session_id=uuid4(),
        context=RunContext.local(revision_id=uuid4()),
    )

    failed = runtime.work_once(worker_id="worker-1")

    assert failed is not None
    assert failed.status is RunStatus.FAILED
    assert any(
        event.type == "run.execution.failed"
        for event in store.list_run_events(failed.id)
    )


def test_worker_restores_security_context_after_process_restart(
    tmp_path: Path,
) -> None:
    seen: list[tuple[str, str]] = []

    class _ContextWorkflow(Workflow):
        @step(entry=True, effects=EffectClass.READ_ONLY)
        def capture(self, state, context):  # type: ignore[no-untyped-def]
            seen.append(
                (
                    context.request.security.tenant_id,
                    context.request.security.principal.id,
                )
            )
            return state

        def forward(self, session: Session) -> Session:
            return session

    path = tmp_path / "runtime.db"
    revision_id = uuid4()
    workflow = _ContextWorkflow()
    first_store = SQLiteRunStore(path)
    first = LocalRuntime(first_store)
    first.submit(
        workflow,
        session_id=uuid4(),
        context=RunContext(
            security=SecurityContext(
                principal=Principal(id="user-42", kind=PrincipalKind.USER),
                tenant_id="tenant-42",
                grants=frozenset({"tool.read"}),
            ),
            revision_id=revision_id,
        ),
    )
    first_store.close()

    second_store = SQLiteRunStore(path)
    second = LocalRuntime(second_store)
    second.register(workflow, revision_id=revision_id)
    completed = second.work_once(worker_id="worker-after-restart")

    assert completed is not None
    assert completed.status is RunStatus.SUCCEEDED
    assert seen == [("tenant-42", "user-42")]


def test_runtime_retries_declared_idempotent_step(tmp_path: Path) -> None:
    attempts = 0

    class _Retry(Workflow):
        @step(
            entry=True,
            effects=EffectClass.IDEMPOTENT,
            idempotency_key="run-step",
            retry=RetryPolicy(max_attempts=3, base_seconds=0.001),
        )
        def unstable(self, state, context):  # type: ignore[no-untyped-def]
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ConnectionError("temporary")
            return {"ok": True}

        def forward(self, session: Session) -> Session:
            return session

    store = SQLiteRunStore(tmp_path / "runtime.db")
    runtime = LocalRuntime(store)
    submitted = runtime.submit(
        _Retry(),
        session_id=uuid4(),
        context=RunContext.local(revision_id=uuid4()),
    )
    completed = runtime.work_once(worker_id="worker")

    assert completed is not None and completed.status is RunStatus.SUCCEEDED
    assert attempts == 3
    failures = [
        event
        for event in store.list_run_events(submitted.id)
        if event.type == "run.step.attempt.failed"
    ]
    assert len(failures) == 2


def test_runtime_enforces_async_step_timeout(tmp_path: Path) -> None:
    import asyncio

    class _Timeout(Workflow):
        @step(
            entry=True,
            effects=EffectClass.READ_ONLY,
            timeout_seconds=0.01,
        )
        async def slow(self, state, context):  # type: ignore[no-untyped-def]
            await asyncio.sleep(1)
            return state

        def forward(self, session: Session) -> Session:
            return session

    store = SQLiteRunStore(tmp_path / "runtime.db")
    runtime = LocalRuntime(store)
    runtime.submit(
        _Timeout(),
        session_id=uuid4(),
        context=RunContext.local(revision_id=uuid4()),
    )
    completed = runtime.work_once(worker_id="worker")

    assert completed is not None
    assert completed.status is RunStatus.TIMED_OUT


def test_runtime_durably_suspends_and_resumes_human_decision(
    tmp_path: Path,
) -> None:
    class _Approval(Workflow):
        @step(entry=True, effects=EffectClass.NON_IDEMPOTENT)
        def approve(self, state, context):  # type: ignore[no-untyped-def]
            decision = context.interrupt(
                InterruptKind.APPROVAL,
                {"tool": "email.send", "arguments": {"to": "user@example.com"}},
            )
            return {
                "decision": decision.kind.value,
                "edited": decision.payload.get("arguments"),
            }

        def forward(self, session: Session) -> Session:
            return session

    store = SQLiteRunStore(tmp_path / "runtime.db")
    runtime = LocalRuntime(store)
    submitted = runtime.submit(
        _Approval(),
        session_id=uuid4(),
        context=RunContext.local(revision_id=uuid4()),
    )

    waiting = runtime.work_once(worker_id="worker-1")
    assert waiting is not None and waiting.status is RunStatus.WAITING
    (interrupt,) = store.list_interrupts(tenant_id="local")
    resumed = store.decide_interrupt(
        interrupt.id,
        decision=ApprovalDecision(
            kind=ApprovalDecisionKind.EDIT,
            actor_id="reviewer",
            reason="replace recipient",
            payload={"arguments": {"to": "safe@example.com"}},
        ),
        expected_run_version=waiting.version,
    )
    assert resumed.status is RunStatus.QUEUED

    completed = runtime.work_once(worker_id="worker-2")
    assert completed is not None and completed.status is RunStatus.SUCCEEDED
    assert completed.id == submitted.id
    assert completed.state["decision"] == "edit"
    assert completed.state["edited"] == {"to": "safe@example.com"}
    assert len(store.list_interrupts(tenant_id="local", pending_only=False)) == 1
