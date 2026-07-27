from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from rath.runtime import ConflictError, Run, RunStatus, SQLiteRunStore


def _run() -> Run:
    return Run.create(
        plan_id=uuid4(),
        revision_id=uuid4(),
        session_id=uuid4(),
        tenant_id="tenant-1",
        next_nodes=("start",),
    )


def test_claim_prefers_higher_priority_then_fifo(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "runtime.db")
    low = store.create_run(
        Run.create(
            plan_id=uuid4(),
            revision_id=uuid4(),
            session_id=uuid4(),
            tenant_id="tenant-1",
            priority=0,
        )
    )
    high = store.create_run(
        Run.create(
            plan_id=uuid4(),
            revision_id=uuid4(),
            session_id=uuid4(),
            tenant_id="tenant-2",
            priority=10,
        )
    )

    claim = store.claim_next(worker_id="worker", lease_seconds=30)

    assert claim is not None
    assert claim.run.id == high.id
    assert claim.run.id != low.id


def test_claim_is_exclusive_and_moves_run_to_running(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "runtime.db")
    queued = store.create_run(_run())

    claim = store.claim_next(worker_id="worker-1", lease_seconds=30)

    assert claim is not None
    assert claim.run.id == queued.id
    assert claim.run.status is RunStatus.RUNNING
    assert claim.lease.holder_worker_id == "worker-1"
    assert claim.lease.fencing_token == 1
    assert store.claim_next(worker_id="worker-2", lease_seconds=30) is None


def test_concurrent_claim_has_single_winner(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "runtime.db")
    store.create_run(_run())
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(
            pool.map(
                lambda index: store.claim_next(
                    worker_id=f"worker-{index}",
                    lease_seconds=30,
                ),
                range(8),
            )
        )

    winners = [claim for claim in claims if claim is not None]
    assert len(winners) == 1


def test_lease_renewal_rejects_stale_fencing_token(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "runtime.db")
    store.create_run(_run())
    claim = store.claim_next(worker_id="worker-1", lease_seconds=30)
    assert claim is not None

    renewed = store.renew_lease(
        claim.run.id,
        worker_id="worker-1",
        fencing_token=claim.lease.fencing_token,
        lease_seconds=60,
    )
    assert renewed.expires_at > claim.lease.expires_at

    with pytest.raises(ConflictError, match="fencing"):
        store.renew_lease(
            claim.run.id,
            worker_id="worker-1",
            fencing_token=0,
            lease_seconds=60,
        )


def test_expired_lease_is_requeued_with_new_fencing_token(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "runtime.db")
    store.create_run(_run())
    first = store.claim_next(worker_id="worker-1", lease_seconds=1)
    assert first is not None
    future = datetime.now(timezone.utc) + timedelta(seconds=2)

    recovered = store.requeue_expired_leases(now=future)
    second = store.claim_next(worker_id="worker-2", lease_seconds=30, now=future)

    assert recovered == (first.run.id,)
    assert second is not None
    assert second.run.id == first.run.id
    assert second.lease.fencing_token == 2
    with pytest.raises(ConflictError, match="fencing"):
        store.assert_fencing_token(
            first.run.id,
            worker_id="worker-1",
            fencing_token=first.lease.fencing_token,
        )
