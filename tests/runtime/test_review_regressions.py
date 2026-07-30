from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

from rath.context import RunContext
from rath.definition import EffectClass, step
from rath.flow import Workflow
from rath.runtime import (
    Checkpoint,
    LocalRuntime,
    RunStatus,
    SQLiteEffectLedger,
    SQLiteRunStore,
    arguments_digest,
)
from rath.session import Session


def test_sync_timeout_does_not_report_terminal_while_handler_runs(
    tmp_path: Path,
) -> None:
    effects: list[str] = []

    class _SyncTimeout(Workflow):
        @step(
            entry=True,
            effects=EffectClass.READ_ONLY,
            timeout_seconds=0.01,
        )
        def slow(self, state, context):  # type: ignore[no-untyped-def]
            time.sleep(0.05)
            effects.append("completed")
            return state

        def forward(self, session: Session) -> Session:
            return session

    store = SQLiteRunStore(tmp_path / "runtime.db")
    runtime = LocalRuntime(store)
    runtime.submit(
        _SyncTimeout(),
        session_id=uuid4(),
        context=RunContext.local(revision_id=uuid4()),
    )

    started = time.perf_counter()
    completed = runtime.work_once(worker_id="worker")
    elapsed = time.perf_counter() - started

    assert completed is not None
    assert completed.status is RunStatus.TIMED_OUT
    assert elapsed >= 0.05
    assert effects == ["completed"]


def test_checkpoint_false_skips_non_terminal_checkpoint(tmp_path: Path) -> None:
    class _NoCheckpoint(Workflow):
        @step(
            entry=True,
            successors=("finish",),
            effects=EffectClass.READ_ONLY,
            checkpoint=False,
        )
        def start(self, state, context):  # type: ignore[no-untyped-def]
            return {**state, "started": True}

        @step(effects=EffectClass.READ_ONLY)
        def finish(self, state, context):  # type: ignore[no-untyped-def]
            return {**state, "finished": True}

        def forward(self, session: Session) -> Session:
            return session

    store = SQLiteRunStore(tmp_path / "runtime.db")
    runtime = LocalRuntime(store)
    run = runtime.submit(
        _NoCheckpoint(),
        session_id=uuid4(),
        context=RunContext.local(revision_id=uuid4()),
    )
    completed = runtime.work_once(worker_id="worker")

    assert completed is not None
    assert completed.status is RunStatus.SUCCEEDED
    checkpoints = store.list_checkpoints(run.id)
    assert len(checkpoints) == 1
    assert checkpoints[0].state["finished"] is True


def test_runtime_enforces_declared_input_and_state_schema(tmp_path: Path) -> None:
    class _SchemaWorkflow(Workflow):
        input_schema = {
            "type": "object",
            "required": ["count"],
            "properties": {"count": {"type": "integer"}},
        }
        state_schema = {
            "type": "object",
            "required": ["count"],
            "properties": {"count": {"type": "integer"}},
        }

        @step(entry=True, effects=EffectClass.READ_ONLY)
        def corrupt(self, state, context):  # type: ignore[no-untyped-def]
            return {"count": "not-an-integer"}

        def forward(self, session: Session) -> Session:
            return session

    store = SQLiteRunStore(tmp_path / "runtime.db")
    runtime = LocalRuntime(store)

    try:
        runtime.submit(
            _SchemaWorkflow(),
            session_id=uuid4(),
            context=RunContext.local(revision_id=uuid4()),
            state={"count": "bad"},
        )
    except Exception as exc:
        assert type(exc).__name__ == "SchemaValidationError"
    else:
        raise AssertionError("invalid input schema was accepted")

    run = runtime.submit(
        _SchemaWorkflow(),
        session_id=uuid4(),
        context=RunContext.local(revision_id=uuid4()),
        state={"count": 1},
    )
    completed = runtime.work_once(worker_id="worker")

    assert completed is not None
    assert completed.status is RunStatus.FAILED
    assert store.list_checkpoints(run.id) == ()


def test_checkpoint_records_effect_watermark(tmp_path: Path) -> None:
    class _EffectWorkflow(Workflow):
        @step(entry=True, effects=EffectClass.READ_ONLY)
        def finish(self, state, context):  # type: ignore[no-untyped-def]
            return state

        def forward(self, session: Session) -> Session:
            return session

    path = tmp_path / "runtime.db"
    store = SQLiteRunStore(path)
    ledger = SQLiteEffectLedger(str(path))
    runtime = LocalRuntime(store, effect_ledger=ledger)
    run = runtime.submit(
        _EffectWorkflow(),
        session_id=uuid4(),
        context=RunContext.local(revision_id=uuid4()),
    )
    invocation = ledger.prepare(
        run_id=run.id,
        tool_name="lookup@1",
        effect_class=EffectClass.READ_ONLY,
        arguments_digest=arguments_digest({}),
        idempotency_key="lookup",
    )
    ledger.complete(invocation.id, {"ok": True})

    completed = runtime.work_once(worker_id="worker")

    assert completed is not None
    assert store.list_checkpoints(run.id)[0].effect_watermark == 1


def test_runtime_fails_closed_on_checkpoint_plan_mismatch(
    tmp_path: Path,
) -> None:
    class _ResumeWorkflow(Workflow):
        @step(entry=True, effects=EffectClass.READ_ONLY)
        def finish(self, state, context):  # type: ignore[no-untyped-def]
            return state

        def forward(self, session: Session) -> Session:
            return session

    store = SQLiteRunStore(tmp_path / "runtime.db")
    runtime = LocalRuntime(store)
    run = runtime.submit(
        _ResumeWorkflow(),
        session_id=uuid4(),
        context=RunContext.local(revision_id=uuid4()),
    )
    store.append_checkpoint(
        Checkpoint.create(
            run_id=run.id,
            sequence=1,
            plan_hash="0" * 64,
            state={},
            next_nodes=("finish",),
            effect_watermark=0,
        )
    )

    completed = runtime.work_once(worker_id="worker")

    assert completed is not None
    assert completed.status is RunStatus.FAILED
    assert any(
        event.data.get("error_type") == "PlanMismatchError"
        for event in store.list_run_events(run.id)
    )
