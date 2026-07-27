"""Durable side-effect ledger and crash ambiguity reconciliation."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Protocol, cast, runtime_checkable
from uuid import UUID, uuid4

from rath._json import JSONValue, freeze_json, thaw_json
from rath.definition import EffectClass
from rath.runtime.models import ConflictError, RunStatus
from rath.runtime.store import RunStore

__all__ = [
    "EffectLedger",
    "InvocationStatus",
    "PostgresEffectLedger",
    "Reconciliation",
    "SQLiteEffectLedger",
    "ToolInvocation",
    "arguments_digest",
    "reconcile_stale_effects",
]


class InvocationStatus(str, Enum):
    PREPARED = "prepared"
    DISPATCHED = "dispatched"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    id: UUID
    run_id: UUID
    tool_name: str
    effect_class: EffectClass
    arguments_digest: str
    status: InvocationStatus
    created_at: datetime
    updated_at: datetime
    idempotency_key: str | None = None
    result: JSONValue | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.tool_name:
            raise ValueError("tool_name must not be empty")
        if len(self.arguments_digest) != 64:
            raise ValueError("arguments_digest must be a SHA-256 digest")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("invocation timestamps must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Reconciliation:
    retryable: tuple[UUID, ...]
    needs_review: tuple[UUID, ...]


@runtime_checkable
class EffectLedger(Protocol):
    def prepare(
        self,
        *,
        run_id: UUID,
        tool_name: str,
        effect_class: EffectClass,
        arguments_digest: str,
        idempotency_key: str | None,
    ) -> ToolInvocation: ...

    def get(self, invocation_id: UUID) -> ToolInvocation: ...

    def mark_dispatched(self, invocation_id: UUID) -> ToolInvocation: ...

    def complete(self, invocation_id: UUID, result: object) -> ToolInvocation: ...

    def fail(self, invocation_id: UUID, error: str) -> ToolInvocation: ...

    def reconcile_stale(
        self, *, older_than: datetime
    ) -> tuple[ToolInvocation, ...]: ...


def arguments_digest(arguments: Mapping[str, object]) -> str:
    frozen = freeze_json(arguments, field="tool arguments")
    encoded = json.dumps(
        thaw_json(frozen),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def reconcile_stale_effects(
    ledger: EffectLedger,
    run_store: RunStore,
    *,
    grace_seconds: float = 30.0,
    now: datetime | None = None,
) -> Reconciliation:
    """Classify dispatched work after a worker crash.

    Idempotent calls may be retried under their stable key. Non-idempotent calls
    are never replayed automatically and move their Run to NEEDS_REVIEW.
    """

    if grace_seconds < 0:
        raise ValueError("grace_seconds must not be negative")
    current = now or datetime.now(timezone.utc)
    stale = ledger.reconcile_stale(
        older_than=current - timedelta(seconds=grace_seconds)
    )
    retryable: list[UUID] = []
    needs_review: list[UUID] = []
    for invocation in stale:
        if invocation.status is InvocationStatus.PREPARED:
            retryable.append(invocation.id)
            continue
        needs_review.append(invocation.id)
        run = run_store.get_run(invocation.run_id)
        if run.status is RunStatus.RUNNING:
            try:
                run_store.transition_run(
                    run.id,
                    expected_version=run.version,
                    target=RunStatus.NEEDS_REVIEW,
                )
            except ConflictError:
                pass
    return Reconciliation(tuple(retryable), tuple(needs_review))


class SQLiteEffectLedger:
    """Effect ledger sharing the embedded runtime SQLite database."""

    def __init__(self, path: str) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def prepare(
        self,
        *,
        run_id: UUID,
        tool_name: str,
        effect_class: EffectClass,
        arguments_digest: str,
        idempotency_key: str | None,
    ) -> ToolInvocation:
        now = datetime.now(timezone.utc)
        invocation = ToolInvocation(
            id=uuid4(),
            run_id=run_id,
            tool_name=tool_name,
            effect_class=effect_class,
            arguments_digest=arguments_digest,
            idempotency_key=idempotency_key,
            status=InvocationStatus.PREPARED,
            created_at=now,
            updated_at=now,
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if idempotency_key is not None:
                row = connection.execute(
                    """
                    SELECT * FROM tool_invocations
                    WHERE run_id = ? AND idempotency_key = ?
                    """,
                    (str(run_id), idempotency_key),
                ).fetchone()
                if row is not None:
                    existing = self._from_row(row)
                    if (
                        existing.arguments_digest != arguments_digest
                        or existing.tool_name != tool_name
                    ):
                        raise ConflictError(
                            "effect idempotency key was reused with different input"
                        )
                    connection.commit()
                    return existing
            connection.execute(
                """
                INSERT INTO tool_invocations(
                    id, run_id, tool_name, effect_class, idempotency_key,
                    arguments_digest, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(invocation.id),
                    str(run_id),
                    tool_name,
                    effect_class.value,
                    idempotency_key,
                    arguments_digest,
                    invocation.status.value,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            connection.commit()
            return invocation
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get(self, invocation_id: UUID) -> ToolInvocation:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM tool_invocations WHERE id = ?",
                (str(invocation_id),),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise KeyError(str(invocation_id))
        return self._from_row(row)

    def mark_dispatched(self, invocation_id: UUID) -> ToolInvocation:
        return self._transition(
            invocation_id,
            expected=(InvocationStatus.PREPARED,),
            target=InvocationStatus.DISPATCHED,
        )

    def complete(self, invocation_id: UUID, result: object) -> ToolInvocation:
        return self._transition(
            invocation_id,
            expected=(InvocationStatus.PREPARED, InvocationStatus.DISPATCHED),
            target=InvocationStatus.SUCCEEDED,
            result=result,
        )

    def fail(self, invocation_id: UUID, error: str) -> ToolInvocation:
        return self._transition(
            invocation_id,
            expected=(InvocationStatus.PREPARED, InvocationStatus.DISPATCHED),
            target=InvocationStatus.FAILED,
            error=error,
        )

    def reconcile_stale(
        self, *, older_than: datetime
    ) -> tuple[ToolInvocation, ...]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT * FROM tool_invocations
                WHERE status = ? AND updated_at <= ?
                ORDER BY created_at, id
                """,
                (InvocationStatus.DISPATCHED.value, older_than.isoformat()),
            ).fetchall()
            output: list[ToolInvocation] = []
            now = datetime.now(timezone.utc).isoformat()
            for row in rows:
                effect = EffectClass(row["effect_class"])
                target = (
                    InvocationStatus.PREPARED
                    if effect
                    in {EffectClass.NONE, EffectClass.READ_ONLY, EffectClass.IDEMPOTENT}
                    else InvocationStatus.AMBIGUOUS
                )
                connection.execute(
                    """
                    UPDATE tool_invocations SET status = ?, updated_at = ?
                    WHERE id = ? AND status = ?
                    """,
                    (
                        target.value,
                        now,
                        row["id"],
                        InvocationStatus.DISPATCHED.value,
                    ),
                )
                updated = dict(row)
                updated["status"] = target.value
                updated["updated_at"] = now
                output.append(self._from_row(updated))
            connection.commit()
            return tuple(output)
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _transition(
        self,
        invocation_id: UUID,
        *,
        expected: tuple[InvocationStatus, ...],
        target: InvocationStatus,
        result: object | None = None,
        error: str | None = None,
    ) -> ToolInvocation:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM tool_invocations WHERE id = ?",
                (str(invocation_id),),
            ).fetchone()
            if row is None:
                raise KeyError(str(invocation_id))
            if InvocationStatus(row["status"]) not in expected:
                raise ConflictError("invalid effect invocation transition")
            now = datetime.now(timezone.utc).isoformat()
            result_json = (
                json.dumps(
                    thaw_json(freeze_json(result, field="tool result")),
                    ensure_ascii=False,
                    sort_keys=True,
                )
                if result is not None
                else None
            )
            connection.execute(
                """
                UPDATE tool_invocations SET status = ?, result_json = ?,
                    error = ?, updated_at = ? WHERE id = ?
                """,
                (target.value, result_json, error, now, str(invocation_id)),
            )
            connection.commit()
            return self.get(invocation_id)
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _from_row(row: Mapping[str, Any]) -> ToolInvocation:
        result = row["result_json"]
        return ToolInvocation(
            id=UUID(row["id"]),
            run_id=UUID(row["run_id"]),
            tool_name=row["tool_name"],
            effect_class=EffectClass(row["effect_class"]),
            idempotency_key=row["idempotency_key"],
            arguments_digest=row["arguments_digest"],
            status=InvocationStatus(row["status"]),
            result=json.loads(result) if isinstance(result, str) else result,
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


class PostgresEffectLedger:
    """Effect ledger sharing a production Postgres Run schema."""

    def __init__(self, dsn: str, *, schema: str = "openrath") -> None:
        from rath.runtime.postgres import PostgresRunStore

        bootstrap = PostgresRunStore(dsn, schema=schema)
        bootstrap.close()
        self.dsn = dsn
        self.schema = schema

    def _connect(self) -> Any:
        import psycopg
        from psycopg import sql
        from psycopg.rows import dict_row

        connection = psycopg.connect(self.dsn, row_factory=dict_row)
        connection.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema))
        )
        return connection

    def prepare(
        self,
        *,
        run_id: UUID,
        tool_name: str,
        effect_class: EffectClass,
        arguments_digest: str,
        idempotency_key: str | None,
    ) -> ToolInvocation:
        now = datetime.now(timezone.utc)
        invocation_id = uuid4()
        connection = self._connect()
        try:
            row = connection.execute(
                """
                INSERT INTO tool_invocations(
                    id, run_id, tool_name, effect_class, idempotency_key,
                    arguments_digest, status, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id, idempotency_key) DO NOTHING RETURNING *
                """,
                (
                    invocation_id,
                    run_id,
                    tool_name,
                    effect_class.value,
                    idempotency_key,
                    arguments_digest,
                    InvocationStatus.PREPARED.value,
                    now,
                    now,
                ),
            ).fetchone()
            if row is None:
                row = connection.execute(
                    """
                    SELECT * FROM tool_invocations
                    WHERE run_id = %s AND idempotency_key = %s FOR UPDATE
                    """,
                    (run_id, idempotency_key),
                ).fetchone()
                if row is None:
                    raise ConflictError("effect invocation already exists")
                if (
                    row["arguments_digest"] != arguments_digest
                    or row["tool_name"] != tool_name
                ):
                    raise ConflictError(
                        "effect idempotency key was reused with different input"
                    )
            connection.commit()
            return self._from_row(row)
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get(self, invocation_id: UUID) -> ToolInvocation:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM tool_invocations WHERE id = %s", (invocation_id,)
            ).fetchone()
            connection.commit()
        finally:
            connection.close()
        if row is None:
            raise KeyError(str(invocation_id))
        return self._from_row(row)

    def mark_dispatched(self, invocation_id: UUID) -> ToolInvocation:
        return self._transition(
            invocation_id,
            expected=(InvocationStatus.PREPARED,),
            target=InvocationStatus.DISPATCHED,
        )

    def complete(self, invocation_id: UUID, result: object) -> ToolInvocation:
        return self._transition(
            invocation_id,
            expected=(InvocationStatus.PREPARED, InvocationStatus.DISPATCHED),
            target=InvocationStatus.SUCCEEDED,
            result=result,
        )

    def fail(self, invocation_id: UUID, error: str) -> ToolInvocation:
        return self._transition(
            invocation_id,
            expected=(InvocationStatus.PREPARED, InvocationStatus.DISPATCHED),
            target=InvocationStatus.FAILED,
            error=error,
        )

    def reconcile_stale(
        self, *, older_than: datetime
    ) -> tuple[ToolInvocation, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM tool_invocations
                WHERE status = %s AND updated_at <= %s
                ORDER BY created_at, id FOR UPDATE SKIP LOCKED
                """,
                (InvocationStatus.DISPATCHED.value, older_than),
            ).fetchall()
            output: list[ToolInvocation] = []
            for row in rows:
                effect = EffectClass(row["effect_class"])
                target = (
                    InvocationStatus.PREPARED
                    if effect
                    in {EffectClass.NONE, EffectClass.READ_ONLY, EffectClass.IDEMPOTENT}
                    else InvocationStatus.AMBIGUOUS
                )
                updated = connection.execute(
                    """
                    UPDATE tool_invocations SET status = %s, updated_at = %s
                    WHERE id = %s AND status = %s RETURNING *
                    """,
                    (
                        target.value,
                        datetime.now(timezone.utc),
                        row["id"],
                        InvocationStatus.DISPATCHED.value,
                    ),
                ).fetchone()
                if updated is not None:
                    output.append(self._from_row(updated))
            connection.commit()
            return tuple(output)
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _transition(
        self,
        invocation_id: UUID,
        *,
        expected: tuple[InvocationStatus, ...],
        target: InvocationStatus,
        result: object | None = None,
        error: str | None = None,
    ) -> ToolInvocation:
        from psycopg.types.json import Jsonb

        result_value = (
            thaw_json(freeze_json(result, field="tool result"))
            if result is not None
            else None
        )
        connection = self._connect()
        try:
            row = connection.execute(
                """
                UPDATE tool_invocations SET status = %s, result_json = %s,
                    error = %s, updated_at = %s
                WHERE id = %s AND status = ANY(%s) RETURNING *
                """,
                (
                    target.value,
                    Jsonb(result_value) if result_value is not None else None,
                    error,
                    datetime.now(timezone.utc),
                    invocation_id,
                    [item.value for item in expected],
                ),
            ).fetchone()
            if row is None:
                raise ConflictError("invalid effect invocation transition")
            connection.commit()
            return self._from_row(row)
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _from_row(row: Mapping[str, Any]) -> ToolInvocation:
        return ToolInvocation(
            id=row["id"],
            run_id=row["run_id"],
            tool_name=row["tool_name"],
            effect_class=EffectClass(row["effect_class"]),
            idempotency_key=row["idempotency_key"],
            arguments_digest=row["arguments_digest"],
            status=InvocationStatus(row["status"]),
            result=cast(JSONValue | None, row["result_json"]),
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
