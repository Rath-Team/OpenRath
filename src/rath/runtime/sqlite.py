"""Transactional SQLite reference store for embedded durable execution."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
from uuid import UUID

from rath._json import freeze_json, thaw_json
from rath.runtime.models import (
    ApprovalDecision,
    ApprovalDecisionKind,
    Checkpoint,
    ClaimedRun,
    ConflictError,
    Interrupt,
    InterruptKind,
    ResourceLease,
    Run,
    RunEvent,
    RunStatus,
    assert_transition,
)

__all__ = ["SQLiteRunStore"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    status TEXT NOT NULL,
    state_json TEXT NOT NULL,
    next_nodes_json TEXT NOT NULL,
    idempotency_key TEXT,
    request_fingerprint TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL,
    UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS runs_tenant_status_idx
    ON runs (tenant_id, status, created_at);

CREATE TABLE IF NOT EXISTS run_events (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    type TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, sequence)
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    plan_hash TEXT NOT NULL,
    state_json TEXT NOT NULL,
    next_nodes_json TEXT NOT NULL,
    pending_interrupts_json TEXT NOT NULL,
    effect_watermark INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (run_id, sequence)
);

CREATE TABLE IF NOT EXISTS interrupts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    request_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decision_kind TEXT,
    decision_actor_id TEXT,
    decision_reason TEXT,
    decision_payload_json TEXT,
    decided_at TEXT
);

CREATE INDEX IF NOT EXISTS interrupts_run_pending_idx
    ON interrupts (run_id, decided_at);

CREATE TABLE IF NOT EXISTS run_leases (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE CASCADE,
    holder_worker_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    fencing_token INTEGER NOT NULL,
    active INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS run_leases_expiry_idx
    ON run_leases (active, expires_at);
"""


def _dump(value: object) -> str:
    frozen = freeze_json(value, field="persistence value")
    return json.dumps(
        thaw_json(frozen),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _load(value: str) -> object:
    return json.loads(value)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("persisted timestamp must be timezone-aware")
    return parsed


class SQLiteRunStore:
    """SQLite source of truth for local mode; every mutation is transactional."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve(strict=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._closed = False
        self._migration_lock = threading.Lock()
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        if self._closed:
            raise RuntimeError("SQLiteRunStore is closed")
        connection = sqlite3.connect(
            str(self.path),
            timeout=30.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _migrate(self) -> None:
        with self._migration_lock:
            connection = self._connect()
            try:
                connection.executescript(_SCHEMA)
                connection.execute(
                    """
                    INSERT OR IGNORE INTO schema_migrations(version, applied_at)
                    VALUES (1, ?)
                    """,
                    (_now().isoformat(),),
                )
            finally:
                connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def close(self) -> None:
        self._closed = True

    def create_run(self, run: Run) -> Run:
        fingerprint = self._fingerprint(run)
        with self._transaction() as connection:
            if run.idempotency_key is not None:
                existing = connection.execute(
                    """
                    SELECT * FROM runs
                    WHERE tenant_id = ? AND idempotency_key = ?
                    """,
                    (run.tenant_id, run.idempotency_key),
                ).fetchone()
                if existing is not None:
                    if existing["request_fingerprint"] != fingerprint:
                        raise ConflictError(
                            "idempotency key was already used for a different request"
                        )
                    return self._run_from_row(existing)
            try:
                connection.execute(
                    """
                    INSERT INTO runs(
                        id, plan_id, revision_id, session_id, tenant_id, status,
                        state_json, next_nodes_json, idempotency_key,
                        request_fingerprint, created_at, updated_at, version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(run.id),
                        str(run.plan_id),
                        str(run.revision_id),
                        str(run.session_id),
                        run.tenant_id,
                        run.status.value,
                        _dump(run.state),
                        _dump(run.next_nodes),
                        run.idempotency_key,
                        fingerprint,
                        run.created_at.isoformat(),
                        run.updated_at.isoformat(),
                        run.version,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError("run already exists") from exc
            self._append_event(
                connection,
                run.id,
                "run.created",
                {"status": run.status.value},
            )
        return run

    def get_run(self, run_id: UUID) -> Run:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM runs WHERE id = ?",
                (str(run_id),),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise KeyError(str(run_id))
        return self._run_from_row(row)

    def list_runs(self, *, tenant_id: str) -> tuple[Run, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM runs WHERE tenant_id = ? ORDER BY created_at, id",
                (tenant_id,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(self._run_from_row(row) for row in rows)

    def transition_run(
        self,
        run_id: UUID,
        *,
        expected_version: int,
        target: RunStatus,
        state: Mapping[str, object] | None = None,
        next_nodes: tuple[str, ...] | None = None,
    ) -> Run:
        with self._transaction() as connection:
            row = self._required_run_row(connection, run_id)
            current = self._run_from_row(row)
            if current.version != expected_version:
                raise ConflictError(
                    "run version conflict",
                    details={
                        "expected_version": expected_version,
                        "actual_version": current.version,
                    },
                )
            assert_transition(current.status, target)
            updated_at = _now()
            next_state = state if state is not None else current.state
            next_queue = next_nodes if next_nodes is not None else current.next_nodes
            cursor = connection.execute(
                """
                UPDATE runs
                SET status = ?, state_json = ?, next_nodes_json = ?,
                    updated_at = ?, version = version + 1
                WHERE id = ? AND version = ?
                """,
                (
                    target.value,
                    _dump(next_state),
                    _dump(next_queue),
                    updated_at.isoformat(),
                    str(run_id),
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError("run version conflict")
            self._append_event(
                connection,
                run_id,
                "run.state.changed",
                {"from": current.status.value, "to": target.value},
            )
            updated_row = self._required_run_row(connection, run_id)
            return self._run_from_row(updated_row)

    def list_run_events(self, run_id: UUID) -> tuple[RunEvent, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM run_events
                WHERE run_id = ? ORDER BY sequence
                """,
                (str(run_id),),
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            RunEvent(
                run_id=UUID(row["run_id"]),
                sequence=int(row["sequence"]),
                type=str(row["type"]),
                data=_load(row["data_json"]),  # type: ignore[arg-type]
                created_at=_parse_time(row["created_at"]),
            )
            for row in rows
        )

    def append_checkpoint(self, checkpoint: Checkpoint) -> None:
        with self._transaction() as connection:
            self._required_run_row(connection, checkpoint.run_id)
            row = connection.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) AS sequence
                FROM checkpoints WHERE run_id = ?
                """,
                (str(checkpoint.run_id),),
            ).fetchone()
            expected = int(row["sequence"]) + 1
            if checkpoint.sequence != expected:
                raise ConflictError(
                    f"checkpoint sequence must be {expected}, got {checkpoint.sequence}"
                )
            connection.execute(
                """
                INSERT INTO checkpoints(
                    id, run_id, sequence, plan_hash, state_json,
                    next_nodes_json, pending_interrupts_json,
                    effect_watermark, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(checkpoint.id),
                    str(checkpoint.run_id),
                    checkpoint.sequence,
                    checkpoint.plan_hash,
                    _dump(checkpoint.state),
                    _dump(checkpoint.next_nodes),
                    _dump(tuple(str(item) for item in checkpoint.pending_interrupts)),
                    checkpoint.effect_watermark,
                    checkpoint.created_at.isoformat(),
                ),
            )
            self._append_event(
                connection,
                checkpoint.run_id,
                "run.checkpoint.created",
                {
                    "checkpoint_id": str(checkpoint.id),
                    "sequence": checkpoint.sequence,
                },
            )

    def latest_checkpoint(self, run_id: UUID) -> Checkpoint | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM checkpoints
                WHERE run_id = ? ORDER BY sequence DESC LIMIT 1
                """,
                (str(run_id),),
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else self._checkpoint_from_row(row)

    def list_checkpoints(self, run_id: UUID) -> tuple[Checkpoint, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM checkpoints
                WHERE run_id = ? ORDER BY sequence
                """,
                (str(run_id),),
            ).fetchall()
        finally:
            connection.close()
        return tuple(self._checkpoint_from_row(row) for row in rows)

    def commit_checkpoint(
        self,
        checkpoint: Checkpoint,
        *,
        worker_id: str,
        fencing_token: int,
        expected_run_version: int,
    ) -> Run:
        with self._transaction() as connection:
            self._required_lease(
                connection,
                checkpoint.run_id,
                worker_id=worker_id,
                fencing_token=fencing_token,
            )
            current = self._run_from_row(
                self._required_run_row(connection, checkpoint.run_id)
            )
            if current.version != expected_run_version:
                raise ConflictError("run version conflict")
            if current.status is not RunStatus.RUNNING:
                raise ConflictError("checkpoint requires a running run")
            row = connection.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) AS sequence
                FROM checkpoints WHERE run_id = ?
                """,
                (str(checkpoint.run_id),),
            ).fetchone()
            expected_sequence = int(row["sequence"]) + 1
            if checkpoint.sequence != expected_sequence:
                raise ConflictError(
                    f"checkpoint sequence must be {expected_sequence}, "
                    f"got {checkpoint.sequence}"
                )
            self._insert_checkpoint(connection, checkpoint)
            connection.execute(
                """
                UPDATE runs
                SET state_json = ?, next_nodes_json = ?, updated_at = ?,
                    version = version + 1
                WHERE id = ? AND version = ?
                """,
                (
                    _dump(checkpoint.state),
                    _dump(checkpoint.next_nodes),
                    checkpoint.created_at.isoformat(),
                    str(checkpoint.run_id),
                    expected_run_version,
                ),
            )
            self._append_event(
                connection,
                checkpoint.run_id,
                "run.checkpoint.created",
                {
                    "checkpoint_id": str(checkpoint.id),
                    "sequence": checkpoint.sequence,
                },
            )
            return self._run_from_row(
                self._required_run_row(connection, checkpoint.run_id)
            )

    def finish_claim(
        self,
        run_id: UUID,
        *,
        worker_id: str,
        fencing_token: int,
        expected_run_version: int,
        target: RunStatus,
        event_type: str = "run.execution.completed",
        event_data: Mapping[str, object] | None = None,
    ) -> Run:
        with self._transaction() as connection:
            self._required_lease(
                connection,
                run_id,
                worker_id=worker_id,
                fencing_token=fencing_token,
            )
            current = self._run_from_row(self._required_run_row(connection, run_id))
            if current.version != expected_run_version:
                raise ConflictError("run version conflict")
            assert_transition(current.status, target)
            self._update_status(
                connection,
                current,
                target=target,
                expected_version=expected_run_version,
            )
            connection.execute(
                """
                UPDATE run_leases SET active = 0, updated_at = ?
                WHERE run_id = ?
                """,
                (_now().isoformat(), str(run_id)),
            )
            self._append_event(
                connection,
                run_id,
                event_type,
                event_data or {"status": target.value},
            )
            return self._run_from_row(self._required_run_row(connection, run_id))

    def create_interrupt(
        self,
        interrupt: Interrupt,
        *,
        expected_run_version: int,
    ) -> Run:
        with self._transaction() as connection:
            row = self._required_run_row(connection, interrupt.run_id)
            current = self._run_from_row(row)
            if current.version != expected_run_version:
                raise ConflictError("run version conflict")
            assert_transition(current.status, RunStatus.WAITING)
            connection.execute(
                """
                INSERT INTO interrupts(
                    id, run_id, kind, request_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(interrupt.id),
                    str(interrupt.run_id),
                    interrupt.kind.value,
                    _dump(interrupt.request),
                    interrupt.created_at.isoformat(),
                ),
            )
            self._update_status(
                connection,
                current,
                target=RunStatus.WAITING,
                expected_version=expected_run_version,
            )
            self._append_event(
                connection,
                interrupt.run_id,
                "run.interrupt.created",
                {"interrupt_id": str(interrupt.id), "kind": interrupt.kind.value},
            )
            return self._run_from_row(
                self._required_run_row(connection, interrupt.run_id)
            )

    def get_interrupt(self, interrupt_id: UUID) -> Interrupt:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM interrupts WHERE id = ?",
                (str(interrupt_id),),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise KeyError(str(interrupt_id))
        return self._interrupt_from_row(row)

    def decide_interrupt(
        self,
        interrupt_id: UUID,
        *,
        decision: ApprovalDecision,
        expected_run_version: int,
    ) -> Run:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM interrupts WHERE id = ?",
                (str(interrupt_id),),
            ).fetchone()
            if row is None:
                raise KeyError(str(interrupt_id))
            if row["decision_kind"] is not None:
                raise ConflictError("interrupt was already decided")
            run_id = UUID(row["run_id"])
            current = self._run_from_row(self._required_run_row(connection, run_id))
            if current.version != expected_run_version:
                raise ConflictError("run version conflict")
            assert_transition(current.status, RunStatus.QUEUED)
            decided_at = _now()
            connection.execute(
                """
                UPDATE interrupts
                SET decision_kind = ?, decision_actor_id = ?,
                    decision_reason = ?, decision_payload_json = ?,
                    decided_at = ?
                WHERE id = ? AND decision_kind IS NULL
                """,
                (
                    decision.kind.value,
                    decision.actor_id,
                    decision.reason,
                    _dump(decision.payload),
                    decided_at.isoformat(),
                    str(interrupt_id),
                ),
            )
            self._update_status(
                connection,
                current,
                target=RunStatus.QUEUED,
                expected_version=expected_run_version,
            )
            self._append_event(
                connection,
                run_id,
                "run.interrupt.decided",
                {
                    "interrupt_id": str(interrupt_id),
                    "decision": decision.kind.value,
                    "actor_id": decision.actor_id,
                },
            )
            return self._run_from_row(self._required_run_row(connection, run_id))

    def claim_next(
        self,
        *,
        worker_id: str,
        lease_seconds: float,
        now: datetime | None = None,
    ) -> ClaimedRun | None:
        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be greater than zero")
        claimed_at = now or _now()
        if claimed_at.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT * FROM runs
                WHERE status = ?
                ORDER BY created_at, id
                LIMIT 1
                """,
                (RunStatus.QUEUED.value,),
            ).fetchone()
            if row is None:
                return None
            current = self._run_from_row(row)
            assert_transition(current.status, RunStatus.RUNNING)
            cursor = connection.execute(
                """
                UPDATE runs
                SET status = ?, updated_at = ?, version = version + 1
                WHERE id = ? AND version = ? AND status = ?
                """,
                (
                    RunStatus.RUNNING.value,
                    claimed_at.isoformat(),
                    str(current.id),
                    current.version,
                    RunStatus.QUEUED.value,
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError("run claim conflict")
            previous = connection.execute(
                "SELECT * FROM run_leases WHERE run_id = ?",
                (str(current.id),),
            ).fetchone()
            lease_id = UUID(previous["id"]) if previous is not None else UUID(
                bytes=hashlib.sha256(str(current.id).encode("utf-8")).digest()[:16]
            )
            token = (
                int(previous["fencing_token"]) + 1 if previous is not None else 1
            )
            created_at = (
                _parse_time(previous["created_at"])
                if previous is not None
                else claimed_at
            )
            expires_at = claimed_at + timedelta(seconds=lease_seconds)
            connection.execute(
                """
                INSERT INTO run_leases(
                    id, run_id, holder_worker_id, expires_at, fencing_token,
                    active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    holder_worker_id = excluded.holder_worker_id,
                    expires_at = excluded.expires_at,
                    fencing_token = excluded.fencing_token,
                    active = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    str(lease_id),
                    str(current.id),
                    worker_id,
                    expires_at.isoformat(),
                    token,
                    created_at.isoformat(),
                    claimed_at.isoformat(),
                ),
            )
            self._append_event(
                connection,
                current.id,
                "run.claimed",
                {"worker_id": worker_id, "fencing_token": token},
            )
            run = self._run_from_row(self._required_run_row(connection, current.id))
            return ClaimedRun(
                run=run,
                lease=ResourceLease(
                    id=lease_id,
                    resource_type="run",
                    resource_id=str(current.id),
                    owner_run_id=current.id,
                    holder_worker_id=worker_id,
                    expires_at=expires_at,
                    fencing_token=token,
                    created_at=created_at,
                    updated_at=claimed_at,
                ),
            )

    def renew_lease(
        self,
        run_id: UUID,
        *,
        worker_id: str,
        fencing_token: int,
        lease_seconds: float,
        now: datetime | None = None,
    ) -> ResourceLease:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be greater than zero")
        renewed_at = now or _now()
        expires_at = renewed_at + timedelta(seconds=lease_seconds)
        with self._transaction() as connection:
            row = self._required_lease(
                connection,
                run_id,
                worker_id=worker_id,
                fencing_token=fencing_token,
            )
            connection.execute(
                """
                UPDATE run_leases
                SET expires_at = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (expires_at.isoformat(), renewed_at.isoformat(), str(run_id)),
            )
            return ResourceLease(
                id=UUID(row["id"]),
                resource_type="run",
                resource_id=str(run_id),
                owner_run_id=run_id,
                holder_worker_id=worker_id,
                expires_at=expires_at,
                fencing_token=fencing_token,
                created_at=_parse_time(row["created_at"]),
                updated_at=renewed_at,
            )

    def assert_fencing_token(
        self,
        run_id: UUID,
        *,
        worker_id: str,
        fencing_token: int,
    ) -> None:
        connection = self._connect()
        try:
            self._required_lease(
                connection,
                run_id,
                worker_id=worker_id,
                fencing_token=fencing_token,
            )
        finally:
            connection.close()

    def requeue_expired_leases(
        self,
        *,
        now: datetime | None = None,
    ) -> tuple[UUID, ...]:
        recovered_at = now or _now()
        with self._transaction() as connection:
            rows = connection.execute(
                """
                SELECT l.*, r.status, r.version
                FROM run_leases l
                JOIN runs r ON r.id = l.run_id
                WHERE l.active = 1 AND l.expires_at <= ?
                ORDER BY l.expires_at, l.run_id
                """,
                (recovered_at.isoformat(),),
            ).fetchall()
            recovered: list[UUID] = []
            for row in rows:
                run_id = UUID(row["run_id"])
                if RunStatus(row["status"]) is not RunStatus.RUNNING:
                    connection.execute(
                        "UPDATE run_leases SET active = 0 WHERE run_id = ?",
                        (str(run_id),),
                    )
                    continue
                connection.execute(
                    """
                    UPDATE runs
                    SET status = ?, updated_at = ?, version = version + 1
                    WHERE id = ? AND version = ?
                    """,
                    (
                        RunStatus.QUEUED.value,
                        recovered_at.isoformat(),
                        str(run_id),
                        int(row["version"]),
                    ),
                )
                connection.execute(
                    """
                    UPDATE run_leases
                    SET active = 0, updated_at = ?
                    WHERE run_id = ?
                    """,
                    (recovered_at.isoformat(), str(run_id)),
                )
                self._append_event(
                    connection,
                    run_id,
                    "run.lease.expired",
                    {"fencing_token": int(row["fencing_token"])},
                )
                recovered.append(run_id)
            return tuple(recovered)

    def _update_status(
        self,
        connection: sqlite3.Connection,
        current: Run,
        *,
        target: RunStatus,
        expected_version: int,
    ) -> None:
        cursor = connection.execute(
            """
            UPDATE runs
            SET status = ?, updated_at = ?, version = version + 1
            WHERE id = ? AND version = ?
            """,
            (
                target.value,
                _now().isoformat(),
                str(current.id),
                expected_version,
            ),
        )
        if cursor.rowcount != 1:
            raise ConflictError("run version conflict")

    def _insert_checkpoint(
        self,
        connection: sqlite3.Connection,
        checkpoint: Checkpoint,
    ) -> None:
        connection.execute(
            """
            INSERT INTO checkpoints(
                id, run_id, sequence, plan_hash, state_json,
                next_nodes_json, pending_interrupts_json,
                effect_watermark, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(checkpoint.id),
                str(checkpoint.run_id),
                checkpoint.sequence,
                checkpoint.plan_hash,
                _dump(checkpoint.state),
                _dump(checkpoint.next_nodes),
                _dump(tuple(str(item) for item in checkpoint.pending_interrupts)),
                checkpoint.effect_watermark,
                checkpoint.created_at.isoformat(),
            ),
        )

    def _append_event(
        self,
        connection: sqlite3.Connection,
        run_id: UUID,
        type: str,
        data: Mapping[str, object],
    ) -> None:
        row = connection.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) AS sequence
            FROM run_events WHERE run_id = ?
            """,
            (str(run_id),),
        ).fetchone()
        sequence = int(row["sequence"]) + 1
        connection.execute(
            """
            INSERT INTO run_events(run_id, sequence, type, data_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(run_id), sequence, type, _dump(data), _now().isoformat()),
        )

    def _required_run_row(
        self,
        connection: sqlite3.Connection,
        run_id: UUID,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM runs WHERE id = ?",
            (str(run_id),),
        ).fetchone()
        if row is None:
            raise KeyError(str(run_id))
        return cast(sqlite3.Row, row)

    def _required_lease(
        self,
        connection: sqlite3.Connection,
        run_id: UUID,
        *,
        worker_id: str,
        fencing_token: int,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM run_leases WHERE run_id = ?",
            (str(run_id),),
        ).fetchone()
        if (
            row is None
            or not bool(row["active"])
            or row["holder_worker_id"] != worker_id
            or int(row["fencing_token"]) != fencing_token
        ):
            raise ConflictError("lease fencing token is stale or not owned")
        return cast(sqlite3.Row, row)

    def _fingerprint(self, run: Run) -> str:
        payload = _dump(
            {
                "plan_id": str(run.plan_id),
                "revision_id": str(run.revision_id),
                "session_id": str(run.session_id),
                "tenant_id": run.tenant_id,
                "state": run.state,
                "next_nodes": run.next_nodes,
            }
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _run_from_row(self, row: sqlite3.Row) -> Run:
        state = _load(row["state_json"])
        next_nodes = _load(row["next_nodes_json"])
        assert isinstance(state, dict)
        assert isinstance(next_nodes, list)
        return Run(
            id=UUID(row["id"]),
            plan_id=UUID(row["plan_id"]),
            revision_id=UUID(row["revision_id"]),
            session_id=UUID(row["session_id"]),
            tenant_id=row["tenant_id"],
            status=RunStatus(row["status"]),
            state=state,
            next_nodes=tuple(str(item) for item in next_nodes),
            idempotency_key=row["idempotency_key"],
            created_at=_parse_time(row["created_at"]),
            updated_at=_parse_time(row["updated_at"]),
            version=int(row["version"]),
        )

    def _checkpoint_from_row(self, row: sqlite3.Row) -> Checkpoint:
        state = _load(row["state_json"])
        next_nodes = _load(row["next_nodes_json"])
        pending = _load(row["pending_interrupts_json"])
        assert isinstance(state, dict)
        assert isinstance(next_nodes, list)
        assert isinstance(pending, list)
        return Checkpoint(
            id=UUID(row["id"]),
            run_id=UUID(row["run_id"]),
            sequence=int(row["sequence"]),
            plan_hash=row["plan_hash"],
            state=state,
            next_nodes=tuple(str(item) for item in next_nodes),
            pending_interrupts=tuple(UUID(str(item)) for item in pending),
            effect_watermark=int(row["effect_watermark"]),
            created_at=_parse_time(row["created_at"]),
        )

    def _interrupt_from_row(self, row: sqlite3.Row) -> Interrupt:
        request = _load(row["request_json"])
        assert isinstance(request, dict)
        decision: ApprovalDecision | None = None
        if row["decision_kind"] is not None:
            payload = _load(row["decision_payload_json"])
            assert isinstance(payload, dict)
            decision = ApprovalDecision(
                kind=ApprovalDecisionKind(row["decision_kind"]),
                actor_id=row["decision_actor_id"],
                reason=row["decision_reason"],
                payload=payload,
            )
        return Interrupt(
            id=UUID(row["id"]),
            run_id=UUID(row["run_id"]),
            kind=InterruptKind(row["kind"]),
            request=request,
            created_at=_parse_time(row["created_at"]),
            decision=decision,
            decided_at=(
                _parse_time(row["decided_at"])
                if row["decided_at"] is not None
                else None
            ),
        )
