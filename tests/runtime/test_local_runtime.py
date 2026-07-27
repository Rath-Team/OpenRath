from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from rath.context import RunContext
from rath.definition import EffectClass, router, step
from rath.flow import Workflow
from rath.runtime import LocalRuntime, RunStatus, SQLiteRunStore
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
    assert any(event.type == "run.execution.failed" for event in store.list_run_events(failed.id))

