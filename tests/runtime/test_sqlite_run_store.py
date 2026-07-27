from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

from rath.runtime import (
    ApprovalDecision,
    ApprovalDecisionKind,
    Checkpoint,
    ConflictError,
    Interrupt,
    InterruptKind,
    Run,
    RunStatus,
    SQLiteRunStore,
)


def _run(*, idempotency_key: str | None = None) -> Run:
    return Run.create(
        plan_id=uuid4(),
        revision_id=uuid4(),
        session_id=uuid4(),
        tenant_id="tenant-1",
        state={"count": 0},
        next_nodes=("start",),
        idempotency_key=idempotency_key,
    )


def test_run_survives_store_reopen(tmp_path: Path) -> None:
    path = tmp_path / "runtime.db"
    first = SQLiteRunStore(path)
    created = first.create_run(_run())
    first.close()

    second = SQLiteRunStore(path)
    loaded = second.get_run(created.id)
    second.close()

    assert loaded == created
    assert loaded.state["count"] == 0


def test_transition_is_compare_and_swap_and_appends_event(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "runtime.db")
    created = store.create_run(_run())
    running = store.transition_run(
        created.id,
        expected_version=0,
        target=RunStatus.RUNNING,
    )

    assert running.status is RunStatus.RUNNING
    assert running.version == 1
    assert [event.type for event in store.list_run_events(created.id)] == [
        "run.created",
        "run.state.changed",
    ]
    with pytest.raises(ConflictError):
        store.transition_run(
            created.id,
            expected_version=0,
            target=RunStatus.FAILED,
        )


def test_idempotency_key_returns_same_run_and_rejects_payload_mismatch(
    tmp_path: Path,
) -> None:
    store = SQLiteRunStore(tmp_path / "runtime.db")
    original = _run(idempotency_key="request-1")
    first = store.create_run(original)
    second = store.create_run(original)

    assert second.id == first.id

    mismatch = Run.create(
        plan_id=uuid4(),
        revision_id=original.revision_id,
        session_id=original.session_id,
        tenant_id=original.tenant_id,
        idempotency_key=original.idempotency_key,
    )
    with pytest.raises(ConflictError, match="different request"):
        store.create_run(mismatch)


def test_concurrent_idempotent_create_has_single_winner(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "runtime.db")
    candidate = _run(idempotency_key="same-request")
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: store.create_run(candidate).id, range(16)))

    assert set(ids) == {candidate.id}
    assert len(store.list_runs(tenant_id="tenant-1")) == 1


def test_checkpoints_are_ordered_and_survive_restart(tmp_path: Path) -> None:
    path = tmp_path / "runtime.db"
    store = SQLiteRunStore(path)
    run = store.create_run(_run())
    checkpoint = Checkpoint.create(
        run_id=run.id,
        sequence=1,
        plan_hash="a" * 64,
        state={"count": 1},
        next_nodes=("next",),
        effect_watermark=0,
    )
    store.append_checkpoint(checkpoint)
    with pytest.raises(ConflictError, match="sequence"):
        store.append_checkpoint(checkpoint)
    store.close()

    reopened = SQLiteRunStore(path)
    loaded = reopened.latest_checkpoint(run.id)
    assert loaded == checkpoint


def test_interrupt_decision_and_waiting_resume_are_atomic(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "runtime.db")
    queued = store.create_run(_run())
    running = store.transition_run(
        queued.id,
        expected_version=queued.version,
        target=RunStatus.RUNNING,
    )
    interrupt = Interrupt.create(
        run_id=running.id,
        kind=InterruptKind.APPROVAL,
        request={"tool": "email.send"},
    )
    waiting = store.create_interrupt(
        interrupt,
        expected_run_version=running.version,
    )
    assert waiting.status is RunStatus.WAITING

    resumed = store.decide_interrupt(
        interrupt.id,
        decision=ApprovalDecision(
            kind=ApprovalDecisionKind.APPROVE,
            actor_id="user-1",
            reason="approved",
        ),
        expected_run_version=waiting.version,
    )

    assert resumed.status is RunStatus.QUEUED
    decided = store.get_interrupt(interrupt.id)
    assert decided.decision is not None
    assert decided.decision.actor_id == "user-1"
    with pytest.raises(ConflictError, match="already decided"):
        store.decide_interrupt(
            interrupt.id,
            decision=ApprovalDecision(
                kind=ApprovalDecisionKind.REJECT,
                actor_id="user-2",
                reason="late",
            ),
            expected_run_version=resumed.version,
        )

