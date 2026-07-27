from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from rath.definition import EffectClass
from rath.runtime import (
    ApprovalDecision,
    ApprovalDecisionKind,
    Checkpoint,
    ConflictError,
    Interrupt,
    InterruptKind,
    PostgresEffectLedger,
    PostgresRunStore,
    Run,
    RunStatus,
    arguments_digest,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("OPENRATH_TEST_POSTGRES_DSN"),
    reason="OPENRATH_TEST_POSTGRES_DSN is not configured",
)


def _run(*, key: str | None = None) -> Run:
    return Run.create(
        plan_id=uuid4(),
        revision_id=uuid4(),
        session_id=uuid4(),
        tenant_id="postgres-test",
        state={"count": 0},
        next_nodes=("start",),
        idempotency_key=key,
    )


@pytest.fixture
def store() -> PostgresRunStore:
    dsn = os.environ["OPENRATH_TEST_POSTGRES_DSN"]
    schema = f"test_{uuid4().hex}"
    value = PostgresRunStore(dsn, schema=schema)
    yield value
    value.close()
    import psycopg
    from psycopg import sql

    with psycopg.connect(dsn) as connection:
        connection.execute(
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
        )


def test_postgres_lifecycle_and_interrupt(store: PostgresRunStore) -> None:
    queued = store.create_run(_run(key="lifecycle"))
    assert store.create_run(queued) == queued
    running = store.transition_run(
        queued.id,
        expected_version=queued.version,
        target=RunStatus.RUNNING,
    )
    checkpoint = Checkpoint.create(
        run_id=running.id,
        sequence=1,
        plan_hash="a" * 64,
        state={"count": 1},
        next_nodes=("approve",),
        effect_watermark=0,
    )
    store.append_checkpoint(checkpoint)
    assert store.latest_checkpoint(running.id) == checkpoint
    interrupt = Interrupt.create(
        run_id=running.id,
        kind=InterruptKind.APPROVAL,
        request={"operation": "email.send"},
    )
    waiting = store.create_interrupt(
        interrupt, expected_run_version=running.version
    )
    resumed = store.decide_interrupt(
        interrupt.id,
        decision=ApprovalDecision(
            kind=ApprovalDecisionKind.APPROVE,
            actor_id="reviewer",
            reason="expected operation",
        ),
        expected_run_version=waiting.version,
    )

    assert resumed.status is RunStatus.QUEUED
    assert store.get_interrupt(interrupt.id).decision is not None
    assert [event.sequence for event in store.list_run_events(queued.id)] == list(
        range(1, len(store.list_run_events(queued.id)) + 1)
    )


def test_postgres_idempotency_and_claim_are_concurrency_safe(
    store: PostgresRunStore,
) -> None:
    candidate = _run(key="same")
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: store.create_run(candidate).id, range(16)))
    assert set(ids) == {candidate.id}

    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(
            pool.map(
                lambda index: store.claim_next(
                    worker_id=f"worker-{index}", lease_seconds=30
                ),
                range(8),
            )
        )
    winners = [claim for claim in claims if claim is not None]
    assert len(winners) == 1
    assert winners[0].run.status is RunStatus.RUNNING


def test_postgres_checkpoint_fencing_and_orphan_recovery(
    store: PostgresRunStore,
) -> None:
    queued = store.create_run(_run())
    first = store.claim_next(worker_id="worker-1", lease_seconds=1)
    assert first is not None
    checkpoint = Checkpoint.create(
        run_id=queued.id,
        sequence=1,
        plan_hash="b" * 64,
        state={"count": 1},
        next_nodes=(),
        effect_watermark=0,
    )
    updated = store.commit_checkpoint(
        checkpoint,
        worker_id="worker-1",
        fencing_token=first.lease.fencing_token,
        expected_run_version=first.run.version,
    )
    future = datetime.now(timezone.utc) + timedelta(seconds=2)
    assert store.requeue_expired_leases(now=future) == (queued.id,)
    second = store.claim_next(
        worker_id="worker-2", lease_seconds=30, now=future
    )
    assert second is not None
    assert second.lease.fencing_token == 2
    with pytest.raises(ConflictError, match="fencing"):
        store.finish_claim(
            updated.id,
            worker_id="worker-1",
            fencing_token=first.lease.fencing_token,
            expected_run_version=updated.version,
            target=RunStatus.SUCCEEDED,
        )


def test_postgres_effect_ledger_persists_ambiguous_dispatch(
    store: PostgresRunStore,
) -> None:
    run = store.create_run(_run())
    running = store.transition_run(
        run.id, expected_version=0, target=RunStatus.RUNNING
    )
    ledger = PostgresEffectLedger(store.dsn, schema=store.schema)
    invocation = ledger.prepare(
        run_id=running.id,
        tool_name="payment.charge@1",
        effect_class=EffectClass.NON_IDEMPOTENT,
        arguments_digest=arguments_digest({"amount": 42}),
        idempotency_key="charge-42",
    )
    dispatched = ledger.mark_dispatched(invocation.id)

    assert dispatched.status.value == "dispatched"
    stale = ledger.reconcile_stale(
        older_than=datetime.now(timezone.utc) + timedelta(seconds=1)
    )
    assert stale[0].status.value == "ambiguous"
