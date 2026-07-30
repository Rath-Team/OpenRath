"""Durable Session and Feedback resource persistence."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

from rath.runtime import PostgresRunStore, RunStore, SQLiteRunStore

__all__ = [
    "AssistantRecord",
    "FeedbackRecord",
    "InMemoryResourceStore",
    "PostgresResourceStore",
    "ResourceStore",
    "SQLiteResourceStore",
    "SessionRecord",
    "default_resource_store",
]


@dataclass(frozen=True, slots=True)
class AssistantRecord:
    id: str
    tenant_id: str
    template_id: str
    revision_id: UUID
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SessionRecord:
    id: UUID
    tenant_id: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class FeedbackRecord:
    id: UUID
    tenant_id: str
    run_id: UUID
    key: str
    score: float | None
    value: str | None
    created_at: datetime


@runtime_checkable
class ResourceStore(Protocol):
    def create_assistant(
        self,
        *,
        tenant_id: str,
        id: str,
        template_id: str,
        revision_id: UUID,
    ) -> AssistantRecord: ...

    def get_assistant(self, tenant_id: str, id: str) -> AssistantRecord: ...

    def list_assistants(self, tenant_id: str) -> tuple[AssistantRecord, ...]: ...

    def create_session(self, tenant_id: str) -> SessionRecord: ...

    def get_session(self, session_id: UUID) -> SessionRecord: ...

    def ensure_session(self, session: SessionRecord) -> SessionRecord: ...

    def count_tenants(self) -> tuple[str, ...]: ...

    def create_feedback(
        self,
        *,
        tenant_id: str,
        run_id: UUID,
        key: str,
        score: float | None,
        value: str | None,
    ) -> FeedbackRecord: ...


class InMemoryResourceStore:
    def __init__(self) -> None:
        self.sessions: dict[UUID, SessionRecord] = {}
        self.feedback: dict[UUID, FeedbackRecord] = {}
        self.assistants: dict[tuple[str, str], AssistantRecord] = {}

    def create_assistant(
        self,
        *,
        tenant_id: str,
        id: str,
        template_id: str,
        revision_id: UUID,
    ) -> AssistantRecord:
        key = (tenant_id, id)
        item = AssistantRecord(
            id, tenant_id, template_id, revision_id, datetime.now(timezone.utc)
        )
        existing = self.assistants.setdefault(key, item)
        if existing.template_id != template_id or existing.revision_id != revision_id:
            raise ValueError("assistant id already has a different revision")
        return existing

    def get_assistant(self, tenant_id: str, id: str) -> AssistantRecord:
        try:
            return self.assistants[(tenant_id, id)]
        except KeyError as exc:
            raise KeyError(id) from exc

    def list_assistants(self, tenant_id: str) -> tuple[AssistantRecord, ...]:
        return tuple(
            value
            for (owner, _), value in sorted(self.assistants.items())
            if owner == tenant_id
        )

    def create_session(self, tenant_id: str) -> SessionRecord:
        value = SessionRecord(uuid4(), tenant_id, datetime.now(timezone.utc))
        self.sessions[value.id] = value
        return value

    def get_session(self, session_id: UUID) -> SessionRecord:
        try:
            return self.sessions[session_id]
        except KeyError as exc:
            raise KeyError(str(session_id)) from exc

    def ensure_session(self, session: SessionRecord) -> SessionRecord:
        existing = self.sessions.setdefault(session.id, session)
        if existing.tenant_id != session.tenant_id:
            raise ValueError("session tenant mismatch")
        return existing

    def count_tenants(self) -> tuple[str, ...]:
        return tuple(sorted({item.tenant_id for item in self.sessions.values()}))

    def create_feedback(
        self,
        *,
        tenant_id: str,
        run_id: UUID,
        key: str,
        score: float | None,
        value: str | None,
    ) -> FeedbackRecord:
        item = FeedbackRecord(
            uuid4(),
            tenant_id,
            run_id,
            key,
            score,
            value,
            datetime.now(timezone.utc),
        )
        self.feedback[item.id] = item
        return item


class SQLiteResourceStore:
    """Resource store sharing the embedded Run database."""

    def __init__(self, run_store: SQLiteRunStore) -> None:
        self.path = str(run_store.path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def create_assistant(
        self,
        *,
        tenant_id: str,
        id: str,
        template_id: str,
        revision_id: UUID,
    ) -> AssistantRecord:
        item = AssistantRecord(
            id, tenant_id, template_id, revision_id, datetime.now(timezone.utc)
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO server_assistants(
                    tenant_id, id, template_id, revision_id, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    id,
                    template_id,
                    str(revision_id),
                    item.created_at.isoformat(),
                ),
            )
        existing = self.get_assistant(tenant_id, id)
        if existing.template_id != template_id or existing.revision_id != revision_id:
            raise ValueError("assistant id already has a different revision")
        return existing

    def get_assistant(self, tenant_id: str, id: str) -> AssistantRecord:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM server_assistants
                WHERE tenant_id = ? AND id = ?
                """,
                (tenant_id, id),
            ).fetchone()
        if row is None:
            raise KeyError(id)
        return AssistantRecord(
            row["id"],
            row["tenant_id"],
            row["template_id"],
            UUID(row["revision_id"]),
            datetime.fromisoformat(row["created_at"]),
        )

    def list_assistants(self, tenant_id: str) -> tuple[AssistantRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM server_assistants
                WHERE tenant_id = ? ORDER BY created_at, id
                """,
                (tenant_id,),
            ).fetchall()
        return tuple(
            AssistantRecord(
                row["id"],
                row["tenant_id"],
                row["template_id"],
                UUID(row["revision_id"]),
                datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        )

    def create_session(self, tenant_id: str) -> SessionRecord:
        value = SessionRecord(uuid4(), tenant_id, datetime.now(timezone.utc))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO server_sessions(id, tenant_id, created_at)
                VALUES (?, ?, ?)
                """,
                (str(value.id), value.tenant_id, value.created_at.isoformat()),
            )
        return value

    def get_session(self, session_id: UUID) -> SessionRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM server_sessions WHERE id = ?", (str(session_id),)
            ).fetchone()
        if row is None:
            raise KeyError(str(session_id))
        return SessionRecord(
            UUID(row["id"]),
            row["tenant_id"],
            datetime.fromisoformat(row["created_at"]),
        )

    def ensure_session(self, session: SessionRecord) -> SessionRecord:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO server_sessions(id, tenant_id, created_at)
                VALUES (?, ?, ?)
                """,
                (str(session.id), session.tenant_id, session.created_at.isoformat()),
            )
        existing = self.get_session(session.id)
        if existing.tenant_id != session.tenant_id:
            raise ValueError("session tenant mismatch")
        return existing

    def count_tenants(self) -> tuple[str, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT tenant_id FROM server_sessions ORDER BY tenant_id"
            ).fetchall()
        return tuple(row["tenant_id"] for row in rows)

    def create_feedback(
        self,
        *,
        tenant_id: str,
        run_id: UUID,
        key: str,
        score: float | None,
        value: str | None,
    ) -> FeedbackRecord:
        item = FeedbackRecord(
            uuid4(),
            tenant_id,
            run_id,
            key,
            score,
            value,
            datetime.now(timezone.utc),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO feedback(
                    id, tenant_id, run_id, key, score, value, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(item.id),
                    item.tenant_id,
                    str(item.run_id),
                    item.key,
                    item.score,
                    item.value,
                    item.created_at.isoformat(),
                ),
            )
        return item


class PostgresResourceStore:
    """Multi-replica resource store sharing the production Run schema."""

    def __init__(self, run_store: PostgresRunStore) -> None:
        self.run_store = run_store

    def create_assistant(
        self,
        *,
        tenant_id: str,
        id: str,
        template_id: str,
        revision_id: UUID,
    ) -> AssistantRecord:
        item = AssistantRecord(
            id, tenant_id, template_id, revision_id, datetime.now(timezone.utc)
        )
        with self.run_store.connection() as connection:
            connection.execute(
                """
                INSERT INTO server_assistants(
                    tenant_id, id, template_id, revision_id, created_at
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, id) DO NOTHING
                """,
                (tenant_id, id, template_id, revision_id, item.created_at),
            )
        existing = self.get_assistant(tenant_id, id)
        if existing.template_id != template_id or existing.revision_id != revision_id:
            raise ValueError("assistant id already has a different revision")
        return existing

    def get_assistant(self, tenant_id: str, id: str) -> AssistantRecord:
        with self.run_store.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM server_assistants
                WHERE tenant_id = %s AND id = %s
                """,
                (tenant_id, id),
            ).fetchone()
        if row is None:
            raise KeyError(id)
        return AssistantRecord(
            row["id"],
            row["tenant_id"],
            row["template_id"],
            row["revision_id"],
            row["created_at"],
        )

    def list_assistants(self, tenant_id: str) -> tuple[AssistantRecord, ...]:
        with self.run_store.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM server_assistants
                WHERE tenant_id = %s ORDER BY created_at, id
                """,
                (tenant_id,),
            ).fetchall()
        return tuple(
            AssistantRecord(
                row["id"],
                row["tenant_id"],
                row["template_id"],
                row["revision_id"],
                row["created_at"],
            )
            for row in rows
        )

    def create_session(self, tenant_id: str) -> SessionRecord:
        value = SessionRecord(uuid4(), tenant_id, datetime.now(timezone.utc))
        with self.run_store.connection() as connection:
            connection.execute(
                """
                INSERT INTO server_sessions(id, tenant_id, created_at)
                VALUES (%s, %s, %s)
                """,
                (value.id, value.tenant_id, value.created_at),
            )
        return value

    def get_session(self, session_id: UUID) -> SessionRecord:
        with self.run_store.connection() as connection:
            row = connection.execute(
                "SELECT * FROM server_sessions WHERE id = %s", (session_id,)
            ).fetchone()
        if row is None:
            raise KeyError(str(session_id))
        return SessionRecord(row["id"], row["tenant_id"], row["created_at"])

    def ensure_session(self, session: SessionRecord) -> SessionRecord:
        with self.run_store.connection() as connection:
            connection.execute(
                """
                INSERT INTO server_sessions(id, tenant_id, created_at)
                VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING
                """,
                (session.id, session.tenant_id, session.created_at),
            )
        existing = self.get_session(session.id)
        if existing.tenant_id != session.tenant_id:
            raise ValueError("session tenant mismatch")
        return existing

    def count_tenants(self) -> tuple[str, ...]:
        with self.run_store.connection() as connection:
            rows = connection.execute(
                "SELECT DISTINCT tenant_id FROM server_sessions ORDER BY tenant_id"
            ).fetchall()
        return tuple(row["tenant_id"] for row in rows)

    def create_feedback(
        self,
        *,
        tenant_id: str,
        run_id: UUID,
        key: str,
        score: float | None,
        value: str | None,
    ) -> FeedbackRecord:
        item = FeedbackRecord(
            uuid4(),
            tenant_id,
            run_id,
            key,
            score,
            value,
            datetime.now(timezone.utc),
        )
        with self.run_store.connection() as connection:
            connection.execute(
                """
                INSERT INTO feedback(
                    id, tenant_id, run_id, key, score, value, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    item.id,
                    item.tenant_id,
                    item.run_id,
                    item.key,
                    item.score,
                    item.value,
                    item.created_at,
                ),
            )
        return item


def default_resource_store(run_store: RunStore) -> ResourceStore:
    if isinstance(run_store, SQLiteRunStore):
        return SQLiteResourceStore(run_store)
    if isinstance(run_store, PostgresRunStore):
        return PostgresResourceStore(run_store)
    return InMemoryResourceStore()
