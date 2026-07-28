from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from rath.definition import EffectClass
from rath.runtime import (
    InvocationStatus,
    Run,
    RunStatus,
    SQLiteEffectLedger,
    SQLiteRunStore,
    arguments_digest,
    reconcile_stale_effects,
)


def _running(store: SQLiteRunStore) -> Run:
    queued = store.create_run(
        Run.create(
            plan_id=uuid4(),
            revision_id=uuid4(),
            session_id=uuid4(),
            tenant_id="tenant",
        )
    )
    return store.transition_run(queued.id, expected_version=0, target=RunStatus.RUNNING)


def test_completed_effect_is_deduplicated(tmp_path: Path) -> None:
    path = tmp_path / "runtime.db"
    store = SQLiteRunStore(path)
    run = _running(store)
    ledger = SQLiteEffectLedger(str(path))
    digest = arguments_digest({"to": "user@example.test"})
    first = ledger.prepare(
        run_id=run.id,
        tool_name="email.send@1",
        effect_class=EffectClass.NON_IDEMPOTENT,
        arguments_digest=digest,
        idempotency_key="email-1",
    )
    ledger.mark_dispatched(first.id)
    completed = ledger.complete(first.id, {"message_id": "m-1"})
    replay = ledger.prepare(
        run_id=run.id,
        tool_name="email.send@1",
        effect_class=EffectClass.NON_IDEMPOTENT,
        arguments_digest=digest,
        idempotency_key="email-1",
    )

    assert completed.status is InvocationStatus.SUCCEEDED
    assert replay == completed


def test_crashed_non_idempotent_effect_requires_review(tmp_path: Path) -> None:
    path = tmp_path / "runtime.db"
    store = SQLiteRunStore(path)
    run = _running(store)
    ledger = SQLiteEffectLedger(str(path))
    invocation = ledger.prepare(
        run_id=run.id,
        tool_name="payment.charge@1",
        effect_class=EffectClass.NON_IDEMPOTENT,
        arguments_digest=arguments_digest({"amount": 10}),
        idempotency_key="charge-1",
    )
    ledger.mark_dispatched(invocation.id)

    result = reconcile_stale_effects(
        ledger,
        store,
        grace_seconds=0,
        now=datetime.now(timezone.utc) + timedelta(seconds=1),
    )

    assert result.needs_review == (invocation.id,)
    assert ledger.get(invocation.id).status is InvocationStatus.AMBIGUOUS
    assert store.get_run(run.id).status is RunStatus.NEEDS_REVIEW


def test_crashed_idempotent_effect_is_retryable(tmp_path: Path) -> None:
    path = tmp_path / "runtime.db"
    store = SQLiteRunStore(path)
    run = _running(store)
    ledger = SQLiteEffectLedger(str(path))
    invocation = ledger.prepare(
        run_id=run.id,
        tool_name="object.put@1",
        effect_class=EffectClass.IDEMPOTENT,
        arguments_digest=arguments_digest({"key": "a"}),
        idempotency_key="put-a",
    )
    ledger.mark_dispatched(invocation.id)
    result = reconcile_stale_effects(
        ledger,
        store,
        grace_seconds=0,
        now=datetime.now(timezone.utc) + timedelta(seconds=1),
    )

    assert result.retryable == (invocation.id,)
    assert ledger.get(invocation.id).status is InvocationStatus.PREPARED
    assert store.get_run(run.id).status is RunStatus.RUNNING


def test_crashed_idempotent_effect_without_key_requires_review(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.db"
    store = SQLiteRunStore(path)
    run = _running(store)
    ledger = SQLiteEffectLedger(str(path))
    invocation = ledger.prepare(
        run_id=run.id,
        tool_name="object.put@1",
        effect_class=EffectClass.IDEMPOTENT,
        arguments_digest=arguments_digest({"key": "a"}),
        idempotency_key=None,
    )
    ledger.mark_dispatched(invocation.id)

    result = reconcile_stale_effects(
        ledger,
        store,
        grace_seconds=0,
        now=datetime.now(timezone.utc) + timedelta(seconds=1),
    )

    assert result.needs_review == (invocation.id,)
    assert ledger.get(invocation.id).status is InvocationStatus.AMBIGUOUS
    assert store.get_run(run.id).status is RunStatus.NEEDS_REVIEW


def test_runtime_reconciles_effects_before_expired_run_requeue(
    tmp_path: Path,
) -> None:
    from rath.runtime import LocalRuntime

    path = tmp_path / "runtime.db"
    store = SQLiteRunStore(path)
    run = _running(store)
    ledger = SQLiteEffectLedger(str(path))
    invocation = ledger.prepare(
        run_id=run.id,
        tool_name="payment.charge@1",
        effect_class=EffectClass.NON_IDEMPOTENT,
        arguments_digest=arguments_digest({"amount": 10}),
        idempotency_key="charge-1",
    )
    ledger.mark_dispatched(invocation.id)
    runtime = LocalRuntime(store, effect_ledger=ledger)

    result = runtime.reconcile_effects(
        grace_seconds=0,
        now=datetime.now(timezone.utc) + timedelta(seconds=1),
    )

    assert result.needs_review == (invocation.id,)
    assert store.get_run(run.id).status is RunStatus.NEEDS_REVIEW
