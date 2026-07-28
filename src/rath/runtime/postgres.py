"""PostgreSQL source-of-truth Run store for multi-worker production mode."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from importlib.resources import files
from typing import Any, cast
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

__all__ = ["PostgresRunStore"]

_SCHEMA_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: object) -> object:
    from psycopg.types.json import Jsonb

    return Jsonb(thaw_json(freeze_json(value, field="persistence value")))


class PostgresRunStore:
    """Transactional Postgres store using row locks and fencing tokens."""

    def __init__(
        self,
        dsn: str,
        *,
        schema: str = "openrath",
        auto_migrate: bool = False,
        pool_max_size: int = 20,
    ) -> None:
        if not dsn.strip():
            raise ValueError("dsn must not be empty")
        if not _SCHEMA_NAME.fullmatch(schema):
            raise ValueError("schema must be a safe lowercase PostgreSQL identifier")
        self.dsn = dsn
        self.schema = schema
        self._closed = False
        if pool_max_size < 1:
            raise ValueError("pool_max_size must be positive")
        if auto_migrate:
            self.migrate(dsn, schema=schema)
        try:
            from psycopg import sql
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
        except ImportError as exc:
            raise RuntimeError(
                "Postgres support requires `pip install openrath[postgres]`"
            ) from exc
        self._sql = sql
        self._pool = ConnectionPool(
            self.dsn,
            min_size=1,
            max_size=pool_max_size,
            timeout=10,
            kwargs={"row_factory": dict_row},
            configure=self._configure_connection,
            open=True,
        )

    def _configure_connection(self, connection: Any) -> None:
        connection.execute(
            self._sql.SQL("SET search_path TO {}").format(
                self._sql.Identifier(self.schema)
            )
        )
        connection.commit()

    @staticmethod
    def _migrations() -> tuple[tuple[int, str, str, str], ...]:
        root = files("rath.runtime").joinpath("migrations/postgres")
        output: list[tuple[int, str, str, str]] = []
        for item in root.iterdir():
            match = re.fullmatch(r"(\d{4})_[a-z0-9_]+\.sql", item.name)
            if match is None:
                continue
            migration = item.read_text(encoding="utf-8")
            output.append(
                (
                    int(match.group(1)),
                    item.name,
                    migration,
                    hashlib.sha256(migration.encode("utf-8")).hexdigest(),
                )
            )
        output.sort(key=lambda item: item[0])
        expected = list(range(1, len(output) + 1))
        if [item[0] for item in output] != expected:
            raise RuntimeError("PostgreSQL migrations must be contiguous from 0001")
        return tuple(output)

    @classmethod
    def migrate(cls, dsn: str, *, schema: str = "openrath") -> None:
        if not dsn.strip():
            raise ValueError("dsn must not be empty")
        if not _SCHEMA_NAME.fullmatch(schema):
            raise ValueError("schema must be a safe lowercase PostgreSQL identifier")
        try:
            import psycopg
            from psycopg import sql
        except ImportError as exc:
            raise RuntimeError(
                "Postgres support requires `pip install openrath[postgres]`"
            ) from exc
        migrations = cls._migrations()
        with psycopg.connect(dsn) as connection:
            connection.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema))
            )
            connection.execute(
                sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
            )
            table_row = connection.execute(
                "SELECT to_regclass('schema_migrations')"
            ).fetchone()
            table_exists = table_row[0] if table_row is not None else None
            for migration_version, filename, migration, checksum in migrations:
                existing = (
                    connection.execute(
                        "SELECT version FROM schema_migrations WHERE version = %s",
                        (migration_version,),
                    ).fetchone()
                    if table_exists is not None
                    else None
                )
                if existing is not None:
                    continue
                connection.execute(migration)
                table_exists = "schema_migrations"
                if migration_version == 1:
                    connection.execute(
                        """
                        INSERT INTO schema_migrations(version, applied_at)
                        VALUES (%s, %s)
                        """,
                        (migration_version, _now()),
                    )
                else:
                    connection.execute(
                        """
                        INSERT INTO schema_migrations(
                            version, filename, checksum, applied_at
                        ) VALUES (%s, %s, %s, %s)
                        """,
                        (migration_version, filename, checksum, _now()),
                    )
            # Migration 0002 introduces checksum metadata. Backfill the
            # immutable 0001 identity for legacy schemas after it is applied.
            first = migrations[0]
            connection.execute(
                """
                UPDATE schema_migrations
                SET filename = COALESCE(filename, %s),
                    checksum = COALESCE(checksum, %s)
                WHERE version = 1
                """,
                (first[1], first[3]),
            )
            for migration_version, filename, _, checksum in migrations:
                row = connection.execute(
                    """
                    SELECT filename, checksum FROM schema_migrations
                    WHERE version = %s
                    """,
                    (migration_version,),
                ).fetchone()
                if row != (filename, checksum):
                    raise RuntimeError(f"migration {filename} checksum mismatch")

    @classmethod
    def verify_schema(cls, dsn: str, *, schema: str = "openrath") -> None:
        if not _SCHEMA_NAME.fullmatch(schema):
            raise ValueError("schema must be a safe lowercase PostgreSQL identifier")
        import psycopg
        from psycopg import sql

        migrations = cls._migrations()
        required_tables = {
            "runs",
            "run_events",
            "checkpoints",
            "interrupts",
            "run_leases",
            "tool_invocations",
        }
        with psycopg.connect(dsn) as connection:
            migration_rows = connection.execute(
                sql.SQL(
                    """
                    SELECT version, filename, checksum
                    FROM {}.schema_migrations ORDER BY version
                    """
                ).format(sql.Identifier(schema))
            ).fetchall()
            rows = connection.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = %s
                """,
                (schema,),
            ).fetchall()
            column_rows = connection.execute(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name IN ('schema_migrations', 'tool_invocations')
                """,
                (schema,),
            ).fetchall()
        expected_rows = [
            (migration_version, filename, checksum)
            for migration_version, filename, _, checksum in migrations
        ]
        if migration_rows != expected_rows:
            raise RuntimeError("OpenRath schema migration checksums are not current")
        present = {str(value[0]) for value in rows}
        missing = required_tables - present
        if missing:
            raise RuntimeError(f"OpenRath schema is missing tables: {sorted(missing)}")
        present_columns = {(str(row[0]), str(row[1])) for row in column_rows}
        required_columns = {
            ("schema_migrations", "filename"),
            ("schema_migrations", "checksum"),
            ("tool_invocations", "node_id"),
            ("tool_invocations", "checkpoint_sequence"),
            ("tool_invocations", "invocation_sequence"),
        }
        missing_columns = required_columns - present_columns
        if missing_columns:
            raise RuntimeError(
                f"OpenRath schema is missing columns: {sorted(missing_columns)}"
            )

    @contextmanager
    def _transaction(self) -> Iterator[Any]:
        if self._closed:
            raise RuntimeError("PostgresRunStore is closed")
        with self._pool.connection() as connection:
            yield connection

    @contextmanager
    def connection(self) -> Iterator[Any]:
        """Borrow a schema-configured pooled connection for related stores."""
        with self._transaction() as connection:
            yield connection

    def close(self) -> None:
        if not self._closed:
            self._pool.close()
        self._closed = True

    def create_run(self, run: Run) -> Run:
        fingerprint = self._fingerprint(run)
        with self._transaction() as connection:
            if run.idempotency_key is not None:
                existing = connection.execute(
                    """
                    SELECT * FROM runs
                    WHERE tenant_id = %s AND idempotency_key = %s
                    FOR UPDATE
                    """,
                    (run.tenant_id, run.idempotency_key),
                ).fetchone()
                if existing is not None:
                    if existing["request_fingerprint"] != fingerprint:
                        raise ConflictError(
                            "idempotency key was already used for a different request"
                        )
                    return self._run_from_row(existing)
            inserted = connection.execute(
                """
                    INSERT INTO runs(
                        id, plan_id, revision_id, session_id, tenant_id, status,
                        state_json, next_nodes_json, idempotency_key, context_json,
                        priority,
                        request_fingerprint, created_at, updated_at, version
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT DO NOTHING
                    RETURNING id
                    """,
                (
                    run.id,
                    run.plan_id,
                    run.revision_id,
                    run.session_id,
                    run.tenant_id,
                    run.status.value,
                    _json(run.state),
                    _json(run.next_nodes),
                    run.idempotency_key,
                    _json(run.context),
                    run.priority,
                    fingerprint,
                    run.created_at,
                    run.updated_at,
                    run.version,
                ),
            ).fetchone()
            if inserted is None:
                if run.idempotency_key is not None:
                    existing = connection.execute(
                        """
                        SELECT * FROM runs
                        WHERE tenant_id = %s AND idempotency_key = %s
                        """,
                        (run.tenant_id, run.idempotency_key),
                    ).fetchone()
                    if (
                        existing is not None
                        and existing["request_fingerprint"] == fingerprint
                    ):
                        return self._run_from_row(existing)
                raise ConflictError("run already exists")
            self._append_event(
                connection, run.id, "run.created", {"status": run.status.value}
            )
        return run

    def get_run(self, run_id: UUID) -> Run:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE id = %s", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(str(run_id))
        return self._run_from_row(row)

    def list_runs(
        self,
        *,
        tenant_id: str,
        after: UUID | None = None,
        limit: int | None = None,
        session_id: UUID | None = None,
        statuses: tuple[RunStatus, ...] | None = None,
    ) -> tuple[Run, ...]:
        if limit is not None and limit < 1:
            raise ValueError("limit must be positive")
        with self._transaction() as connection:
            clauses = ["tenant_id = %s"]
            parameters: list[object] = [tenant_id]
            if after is not None:
                cursor = connection.execute(
                    """
                    SELECT created_at, id FROM runs
                    WHERE id = %s AND tenant_id = %s
                    """,
                    (after, tenant_id),
                ).fetchone()
                if cursor is None:
                    raise KeyError(str(after))
                clauses.append("(created_at, id) > (%s, %s)")
                parameters.extend((cursor["created_at"], cursor["id"]))
            if session_id is not None:
                clauses.append("session_id = %s")
                parameters.append(session_id)
            if statuses:
                clauses.append("status = ANY(%s)")
                parameters.append([item.value for item in statuses])
            suffix = " LIMIT %s" if limit is not None else ""
            if limit is not None:
                parameters.append(limit)
            rows = connection.execute(
                f"""
                SELECT * FROM runs WHERE {" AND ".join(clauses)}
                ORDER BY created_at, id{suffix}
                """,
                parameters,
            ).fetchall()
        return tuple(self._run_from_row(row) for row in rows)

    def count_runs(
        self,
        *,
        status: RunStatus,
        tenant_id: str | None = None,
    ) -> int:
        with self._transaction() as connection:
            if tenant_id is None:
                row = connection.execute(
                    "SELECT COUNT(*) AS value FROM runs WHERE status = %s",
                    (status.value,),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT COUNT(*) AS value FROM runs
                    WHERE status = %s AND tenant_id = %s
                    """,
                    (status.value, tenant_id),
                ).fetchone()
        return int(row["value"])

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
            current = self._run_from_row(self._required_run_row(connection, run_id))
            if current.version != expected_version:
                raise ConflictError("run version conflict")
            assert_transition(current.status, target)
            row = connection.execute(
                """
                UPDATE runs SET status = %s, state_json = %s,
                    next_nodes_json = %s, updated_at = %s, version = version + 1
                WHERE id = %s AND version = %s RETURNING *
                """,
                (
                    target.value,
                    _json(state if state is not None else current.state),
                    _json(next_nodes if next_nodes is not None else current.next_nodes),
                    _now(),
                    run_id,
                    expected_version,
                ),
            ).fetchone()
            if row is None:
                raise ConflictError("run version conflict")
            self._append_event(
                connection,
                run_id,
                "run.state.changed",
                {"from": current.status.value, "to": target.value},
            )
            return self._run_from_row(row)

    def list_run_events(
        self,
        run_id: UUID,
        *,
        after_sequence: int = 0,
        limit: int | None = None,
    ) -> tuple[RunEvent, ...]:
        if after_sequence < 0:
            raise ValueError("after_sequence must not be negative")
        if limit is not None and limit < 1:
            raise ValueError("limit must be positive")
        with self._transaction() as connection:
            suffix = " LIMIT %s" if limit is not None else ""
            parameters: list[object] = [run_id, after_sequence]
            if limit is not None:
                parameters.append(limit)
            rows = connection.execute(
                f"""
                SELECT * FROM run_events
                WHERE run_id = %s AND sequence > %s ORDER BY sequence{suffix}
                """,
                parameters,
            ).fetchall()
        return tuple(
            RunEvent(
                run_id=row["run_id"],
                sequence=int(row["sequence"]),
                type=row["type"],
                data=row["data_json"],
                created_at=row["created_at"],
            )
            for row in rows
        )

    def append_run_event(
        self,
        run_id: UUID,
        type: str,
        data: Mapping[str, object],
    ) -> RunEvent:
        with self._transaction() as connection:
            self._required_run_row(connection, run_id)
            return self._append_event(connection, run_id, type, data)

    def append_checkpoint(self, checkpoint: Checkpoint) -> None:
        with self._transaction() as connection:
            self._required_run_row(connection, checkpoint.run_id, lock=True)
            self._validate_checkpoint_sequence(connection, checkpoint)
            self._insert_checkpoint(connection, checkpoint)
            self._append_event(
                connection,
                checkpoint.run_id,
                "run.checkpoint.created",
                {"checkpoint_id": str(checkpoint.id), "sequence": checkpoint.sequence},
            )

    def latest_checkpoint(self, run_id: UUID) -> Checkpoint | None:
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT * FROM checkpoints
                WHERE run_id = %s ORDER BY sequence DESC LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        return None if row is None else self._checkpoint_from_row(row)

    def list_checkpoints(self, run_id: UUID) -> tuple[Checkpoint, ...]:
        with self._transaction() as connection:
            rows = connection.execute(
                """
                SELECT * FROM checkpoints
                WHERE run_id = %s ORDER BY sequence
                """,
                (run_id,),
            ).fetchall()
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
                self._required_run_row(connection, checkpoint.run_id, lock=True)
            )
            if current.version != expected_run_version:
                raise ConflictError("run version conflict")
            if current.status is not RunStatus.RUNNING:
                raise ConflictError("checkpoint requires a running run")
            self._validate_checkpoint_sequence(connection, checkpoint)
            self._insert_checkpoint(connection, checkpoint)
            row = connection.execute(
                """
                UPDATE runs SET state_json = %s, next_nodes_json = %s,
                    updated_at = %s, version = version + 1
                WHERE id = %s AND version = %s RETURNING *
                """,
                (
                    _json(checkpoint.state),
                    _json(checkpoint.next_nodes),
                    checkpoint.created_at,
                    checkpoint.run_id,
                    expected_run_version,
                ),
            ).fetchone()
            if row is None:
                raise ConflictError("run version conflict")
            self._append_event(
                connection,
                checkpoint.run_id,
                "run.checkpoint.created",
                {"checkpoint_id": str(checkpoint.id), "sequence": checkpoint.sequence},
            )
            return self._run_from_row(row)

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
            current = self._run_from_row(
                self._required_run_row(connection, run_id, lock=True)
            )
            if current.version != expected_run_version:
                raise ConflictError("run version conflict")
            assert_transition(current.status, target)
            row = connection.execute(
                """
                UPDATE runs SET status = %s, updated_at = %s, version = version + 1
                WHERE id = %s AND version = %s RETURNING *
                """,
                (target.value, _now(), run_id, expected_run_version),
            ).fetchone()
            if row is None:
                raise ConflictError("run version conflict")
            connection.execute(
                """
                UPDATE run_leases SET active = FALSE, updated_at = %s
                WHERE run_id = %s
                """,
                (_now(), run_id),
            )
            self._append_event(
                connection,
                run_id,
                event_type,
                event_data or {"status": target.value},
            )
            return self._run_from_row(row)

    def create_interrupt(
        self, interrupt: Interrupt, *, expected_run_version: int
    ) -> Run:
        with self._transaction() as connection:
            current = self._run_from_row(
                self._required_run_row(connection, interrupt.run_id, lock=True)
            )
            if current.version != expected_run_version:
                raise ConflictError("run version conflict")
            assert_transition(current.status, RunStatus.WAITING)
            connection.execute(
                """
                INSERT INTO interrupts(
                    id, run_id, kind, request_json, created_at, expires_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    interrupt.id,
                    interrupt.run_id,
                    interrupt.kind.value,
                    _json(interrupt.request),
                    interrupt.created_at,
                    interrupt.expires_at,
                ),
            )
            row = self._update_status(
                connection,
                current,
                target=RunStatus.WAITING,
                expected_version=expected_run_version,
            )
            connection.execute(
                """
                UPDATE run_leases SET active = FALSE, updated_at = %s
                WHERE run_id = %s
                """,
                (interrupt.created_at, interrupt.run_id),
            )
            self._append_event(
                connection,
                interrupt.run_id,
                "run.interrupt.created",
                {"interrupt_id": str(interrupt.id), "kind": interrupt.kind.value},
            )
            return self._run_from_row(row)

    def get_interrupt(self, interrupt_id: UUID) -> Interrupt:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM interrupts WHERE id = %s", (interrupt_id,)
            ).fetchone()
        if row is None:
            raise KeyError(str(interrupt_id))
        return self._interrupt_from_row(row)

    def list_interrupts(
        self,
        *,
        tenant_id: str,
        pending_only: bool = True,
    ) -> tuple[Interrupt, ...]:
        pending_clause = "AND i.decided_at IS NULL" if pending_only else ""
        with self.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT i.* FROM interrupts AS i
                JOIN runs AS r ON r.id = i.run_id
                WHERE r.tenant_id = %s {pending_clause}
                ORDER BY i.created_at, i.id
                """,
                (tenant_id,),
            ).fetchall()
        return tuple(self._interrupt_from_row(row) for row in rows)

    def expire_interrupts(
        self,
        *,
        now: datetime | None = None,
    ) -> tuple[UUID, ...]:
        expired_at = now or _now()
        if expired_at.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        expired: list[UUID] = []
        with self._transaction() as connection:
            rows = connection.execute(
                """
                SELECT i.*, r.version AS run_version, r.status AS run_status
                FROM interrupts AS i
                JOIN runs AS r ON r.id = i.run_id
                WHERE i.decided_at IS NULL
                  AND i.expires_at IS NOT NULL
                  AND i.expires_at <= %s
                ORDER BY i.expires_at, i.id
                FOR UPDATE OF i, r SKIP LOCKED
                """,
                (expired_at,),
            ).fetchall()
            for row in rows:
                connection.execute(
                    """
                    UPDATE interrupts SET decision_kind = %s,
                        decision_actor_id = %s, decision_reason = %s,
                        decision_payload_json = %s, decided_at = %s
                    WHERE id = %s AND decided_at IS NULL
                    """,
                    (
                        ApprovalDecisionKind.REJECT.value,
                        "openrath-system",
                        "interrupt deadline expired",
                        _json({}),
                        expired_at,
                        row["id"],
                    ),
                )
                if RunStatus(row["run_status"]) is RunStatus.WAITING:
                    current = self._run_from_row(
                        self._required_run_row(connection, row["run_id"], lock=True)
                    )
                    self._update_status(
                        connection,
                        current,
                        target=RunStatus.TIMED_OUT,
                        expected_version=int(row["run_version"]),
                    )
                    self._append_event(
                        connection,
                        row["run_id"],
                        "run.interrupt.expired",
                        {"interrupt_id": str(row["id"])},
                    )
                expired.append(row["id"])
        return tuple(expired)

    def decide_interrupt(
        self,
        interrupt_id: UUID,
        *,
        decision: ApprovalDecision,
        expected_run_version: int,
    ) -> Run:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM interrupts WHERE id = %s FOR UPDATE",
                (interrupt_id,),
            ).fetchone()
            if row is None:
                raise KeyError(str(interrupt_id))
            if row["decision_kind"] is not None:
                raise ConflictError("interrupt was already decided")
            current = self._run_from_row(
                self._required_run_row(connection, row["run_id"], lock=True)
            )
            if current.version != expected_run_version:
                raise ConflictError("run version conflict")
            assert_transition(current.status, RunStatus.QUEUED)
            connection.execute(
                """
                UPDATE interrupts SET decision_kind = %s,
                    decision_actor_id = %s, decision_reason = %s,
                    decision_payload_json = %s, decided_at = %s
                WHERE id = %s AND decision_kind IS NULL
                """,
                (
                    decision.kind.value,
                    decision.actor_id,
                    decision.reason,
                    _json(decision.payload),
                    _now(),
                    interrupt_id,
                ),
            )
            updated = self._update_status(
                connection,
                current,
                target=RunStatus.QUEUED,
                expected_version=expected_run_version,
            )
            self._append_event(
                connection,
                current.id,
                "run.interrupt.decided",
                {
                    "interrupt_id": str(interrupt_id),
                    "decision": decision.kind.value,
                    "actor_id": decision.actor_id,
                },
            )
            return self._run_from_row(updated)

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
                SELECT * FROM runs WHERE status = %s
                ORDER BY priority DESC, created_at, id
                FOR UPDATE SKIP LOCKED LIMIT 1
                """,
                (RunStatus.QUEUED.value,),
            ).fetchone()
            if row is None:
                return None
            current = self._run_from_row(row)
            previous = connection.execute(
                "SELECT * FROM run_leases WHERE run_id = %s FOR UPDATE",
                (current.id,),
            ).fetchone()
            lease_id = (
                previous["id"]
                if previous is not None
                else UUID(bytes=hashlib.sha256(str(current.id).encode()).digest()[:16])
            )
            token = int(previous["fencing_token"]) + 1 if previous else 1
            created_at = previous["created_at"] if previous else claimed_at
            expires_at = claimed_at + timedelta(seconds=lease_seconds)
            updated = connection.execute(
                """
                UPDATE runs SET status = %s, updated_at = %s, version = version + 1
                WHERE id = %s AND version = %s AND status = %s RETURNING *
                """,
                (
                    RunStatus.RUNNING.value,
                    claimed_at,
                    current.id,
                    current.version,
                    RunStatus.QUEUED.value,
                ),
            ).fetchone()
            if updated is None:
                raise ConflictError("run claim conflict")
            connection.execute(
                """
                INSERT INTO run_leases(
                    id, run_id, holder_worker_id, expires_at, fencing_token,
                    active, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, TRUE, %s, %s)
                ON CONFLICT(run_id) DO UPDATE SET
                    holder_worker_id = excluded.holder_worker_id,
                    expires_at = excluded.expires_at,
                    fencing_token = excluded.fencing_token,
                    active = TRUE, updated_at = excluded.updated_at
                """,
                (
                    lease_id,
                    current.id,
                    worker_id,
                    expires_at,
                    token,
                    created_at,
                    claimed_at,
                ),
            )
            self._append_event(
                connection,
                current.id,
                "run.claimed",
                {"worker_id": worker_id, "fencing_token": token},
            )
            return ClaimedRun(
                run=self._run_from_row(updated),
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
                UPDATE run_leases SET expires_at = %s, updated_at = %s
                WHERE run_id = %s
                """,
                (expires_at, renewed_at, run_id),
            )
            return self._lease_from_row(
                {**row, "expires_at": expires_at, "updated_at": renewed_at}
            )

    def assert_fencing_token(
        self, run_id: UUID, *, worker_id: str, fencing_token: int
    ) -> None:
        with self._transaction() as connection:
            self._required_lease(
                connection,
                run_id,
                worker_id=worker_id,
                fencing_token=fencing_token,
            )

    def requeue_expired_leases(
        self, *, now: datetime | None = None
    ) -> tuple[UUID, ...]:
        recovered_at = now or _now()
        with self._transaction() as connection:
            rows = connection.execute(
                """
                SELECT l.*, r.status, r.version FROM run_leases l
                JOIN runs r ON r.id = l.run_id
                WHERE l.active = TRUE AND l.expires_at <= %s
                ORDER BY l.expires_at, l.run_id FOR UPDATE OF l, r SKIP LOCKED
                """,
                (recovered_at,),
            ).fetchall()
            recovered: list[UUID] = []
            for row in rows:
                run_id = row["run_id"]
                if RunStatus(row["status"]) is RunStatus.RUNNING:
                    connection.execute(
                        """
                        UPDATE runs SET status = %s, updated_at = %s,
                            version = version + 1
                        WHERE id = %s AND version = %s
                        """,
                        (
                            RunStatus.QUEUED.value,
                            recovered_at,
                            run_id,
                            row["version"],
                        ),
                    )
                    self._append_event(
                        connection,
                        run_id,
                        "run.lease.expired",
                        {"fencing_token": int(row["fencing_token"])},
                    )
                    recovered.append(run_id)
                connection.execute(
                    """
                    UPDATE run_leases SET active = FALSE, updated_at = %s
                    WHERE run_id = %s
                    """,
                    (recovered_at, run_id),
                )
            return tuple(recovered)

    def _required_run_row(
        self, connection: Any, run_id: UUID, *, lock: bool = False
    ) -> Mapping[str, Any]:
        suffix = " FOR UPDATE" if lock else ""
        row = connection.execute(
            f"SELECT * FROM runs WHERE id = %s{suffix}", (run_id,)
        ).fetchone()
        if row is None:
            raise KeyError(str(run_id))
        return cast(Mapping[str, Any], row)

    def _required_lease(
        self,
        connection: Any,
        run_id: UUID,
        *,
        worker_id: str,
        fencing_token: int,
    ) -> Mapping[str, Any]:
        row = connection.execute(
            "SELECT * FROM run_leases WHERE run_id = %s FOR UPDATE", (run_id,)
        ).fetchone()
        if (
            row is None
            or not row["active"]
            or row["holder_worker_id"] != worker_id
            or int(row["fencing_token"]) != fencing_token
            or row["expires_at"] <= _now()
        ):
            raise ConflictError("lease fencing token is stale or not owned")
        return cast(Mapping[str, Any], row)

    def _update_status(
        self,
        connection: Any,
        current: Run,
        *,
        target: RunStatus,
        expected_version: int,
    ) -> Mapping[str, Any]:
        row = connection.execute(
            """
            UPDATE runs SET status = %s, updated_at = %s, version = version + 1
            WHERE id = %s AND version = %s RETURNING *
            """,
            (target.value, _now(), current.id, expected_version),
        ).fetchone()
        if row is None:
            raise ConflictError("run version conflict")
        return cast(Mapping[str, Any], row)

    def _validate_checkpoint_sequence(
        self, connection: Any, checkpoint: Checkpoint
    ) -> None:
        row = connection.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) AS sequence
            FROM checkpoints WHERE run_id = %s
            """,
            (checkpoint.run_id,),
        ).fetchone()
        expected = int(row["sequence"]) + 1
        if checkpoint.sequence != expected:
            raise ConflictError(
                f"checkpoint sequence must be {expected}, got {checkpoint.sequence}"
            )

    def _insert_checkpoint(self, connection: Any, checkpoint: Checkpoint) -> None:
        connection.execute(
            """
            INSERT INTO checkpoints(
                id, run_id, sequence, plan_hash, state_json,
                next_nodes_json, pending_interrupts_json,
                effect_watermark, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                checkpoint.id,
                checkpoint.run_id,
                checkpoint.sequence,
                checkpoint.plan_hash,
                _json(checkpoint.state),
                _json(checkpoint.next_nodes),
                _json(tuple(str(item) for item in checkpoint.pending_interrupts)),
                checkpoint.effect_watermark,
                checkpoint.created_at,
            ),
        )

    def _append_event(
        self,
        connection: Any,
        run_id: UUID,
        type: str,
        data: Mapping[str, object],
    ) -> RunEvent:
        # Serialize sequence allocation with every other event writer for this
        # Run. MAX(sequence)+1 is safe only while the parent row is locked.
        connection.execute(
            "SELECT id FROM runs WHERE id = %s FOR UPDATE",
            (run_id,),
        ).fetchone()
        row = connection.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) AS sequence
            FROM run_events WHERE run_id = %s
            """,
            (run_id,),
        ).fetchone()
        created_at = _now()
        connection.execute(
            """
            INSERT INTO run_events(run_id, sequence, type, data_json, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (run_id, int(row["sequence"]) + 1, type, _json(data), created_at),
        )
        return RunEvent(
            run_id=run_id,
            sequence=int(row["sequence"]) + 1,
            type=type,
            data=freeze_json(data, field="run event data"),  # type: ignore[arg-type]
            created_at=created_at,
        )

    def _fingerprint(self, run: Run) -> str:
        frozen = freeze_json(
            {
                "plan_id": str(run.plan_id),
                "revision_id": str(run.revision_id),
                "session_id": str(run.session_id),
                "tenant_id": run.tenant_id,
                "state": run.state,
                "next_nodes": run.next_nodes,
                "priority": run.priority,
            },
            field="run fingerprint",
        )
        import json

        payload = json.dumps(
            thaw_json(frozen),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _run_from_row(row: Mapping[str, Any]) -> Run:
        return Run(
            id=row["id"],
            plan_id=row["plan_id"],
            revision_id=row["revision_id"],
            session_id=row["session_id"],
            tenant_id=row["tenant_id"],
            status=RunStatus(row["status"]),
            state=row["state_json"],
            next_nodes=tuple(row["next_nodes_json"]),
            idempotency_key=row["idempotency_key"],
            context=row["context_json"],
            priority=int(row["priority"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            version=int(row["version"]),
        )

    @staticmethod
    def _checkpoint_from_row(row: Mapping[str, Any]) -> Checkpoint:
        return Checkpoint(
            id=row["id"],
            run_id=row["run_id"],
            sequence=int(row["sequence"]),
            plan_hash=row["plan_hash"],
            state=row["state_json"],
            next_nodes=tuple(row["next_nodes_json"]),
            pending_interrupts=tuple(
                UUID(item) for item in row["pending_interrupts_json"]
            ),
            effect_watermark=int(row["effect_watermark"]),
            created_at=row["created_at"],
        )

    @staticmethod
    def _interrupt_from_row(row: Mapping[str, Any]) -> Interrupt:
        decision = None
        if row["decision_kind"] is not None:
            decision = ApprovalDecision(
                kind=ApprovalDecisionKind(row["decision_kind"]),
                actor_id=row["decision_actor_id"],
                reason=row["decision_reason"],
                payload=row["decision_payload_json"],
            )
        return Interrupt(
            id=row["id"],
            run_id=row["run_id"],
            kind=InterruptKind(row["kind"]),
            request=row["request_json"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            decision=decision,
            decided_at=row["decided_at"],
        )

    @staticmethod
    def _lease_from_row(row: Mapping[str, Any]) -> ResourceLease:
        run_id = row["run_id"]
        return ResourceLease(
            id=row["id"],
            resource_type="run",
            resource_id=str(run_id),
            owner_run_id=run_id,
            holder_worker_id=row["holder_worker_id"],
            expires_at=row["expires_at"],
            fencing_token=int(row["fencing_token"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
