from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from rath.context import RunContext
from rath.definition import EffectClass, step
from rath.flow import Workflow
from rath.runtime import LocalRuntime, RunStatus, SQLiteRunStore
from rath.session import Session


def test_cancel_wins_over_late_worker_checkpoint(tmp_path: Path) -> None:
    entered = threading.Event()
    release = threading.Event()

    class _Blocked(Workflow):
        @step(entry=True, effects=EffectClass.READ_ONLY)
        def wait(self, state, context):  # type: ignore[no-untyped-def]
            entered.set()
            release.wait(timeout=5)
            return {"late": True}

        def forward(self, session: Session) -> Session:
            return session

    store = SQLiteRunStore(tmp_path / "runtime.db")
    runtime = LocalRuntime(store)
    submitted = runtime.submit(
        _Blocked(),
        session_id=uuid4(),
        context=RunContext.local(revision_id=uuid4()),
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(runtime.work_once, worker_id="worker", lease_seconds=1)
        assert entered.wait(timeout=2)
        running = store.get_run(submitted.id)
        cancelled = store.transition_run(
            running.id,
            expected_version=running.version,
            target=RunStatus.CANCELLED,
        )
        release.set()
        result = worker.result(timeout=5)

    assert result is not None
    assert result.status is RunStatus.CANCELLED
    assert store.get_run(submitted.id) == cancelled
    assert store.latest_checkpoint(submitted.id) is None


def test_duplicate_submission_does_not_duplicate_execution(tmp_path: Path) -> None:
    executions = 0

    class _Count(Workflow):
        @step(entry=True, effects=EffectClass.IDEMPOTENT)
        def count(self, state, context):  # type: ignore[no-untyped-def]
            nonlocal executions
            executions += 1
            return state

        def forward(self, session: Session) -> Session:
            return session

    store = SQLiteRunStore(tmp_path / "runtime.db")
    runtime = LocalRuntime(store)
    context = RunContext.local(revision_id=uuid4())
    workflow = _Count()
    session_id = uuid4()
    first = runtime.submit(
        workflow,
        session_id=session_id,
        context=context,
        idempotency_key="delivery-1",
    )
    second = runtime.submit(
        workflow,
        session_id=session_id,
        context=context,
        idempotency_key="delivery-1",
    )
    runtime.work_once(worker_id="worker")

    assert first.id == second.id
    assert executions == 1
