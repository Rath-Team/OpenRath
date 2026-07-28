"""Immutable, content-identified deployment revisions."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable
from uuid import NAMESPACE_URL, UUID, uuid5

from rath._json import JSONValue, freeze_mapping, thaw_json
from rath.runtime import PostgresRunStore, SQLiteRunStore

__all__ = [
    "DeploymentManifest",
    "PostgresRevisionStore",
    "Revision",
    "RevisionConflict",
    "RevisionStore",
    "SQLiteRevisionStore",
]


class RevisionConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DeploymentManifest:
    image_digest: str
    plan_hash: str
    python_version: str
    dependencies_digest: str
    resources: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in (
            ("image_digest", self.image_digest),
            ("plan_hash", self.plan_hash),
            ("dependencies_digest", self.dependencies_digest),
        ):
            if len(value) != 64:
                raise ValueError(f"{name} must be a SHA-256 digest")
            int(value, 16)
        object.__setattr__(
            self,
            "resources",
            freeze_mapping(self.resources, field="deployment.resources"),
        )

    def canonical_json(self) -> str:
        return json.dumps(
            {
                "image_digest": self.image_digest,
                "plan_hash": self.plan_hash,
                "python_version": self.python_version,
                "dependencies_digest": self.dependencies_digest,
                "resources": thaw_json(self.resources),
            },
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class Revision:
    id: UUID
    code_digest: str
    manifest: DeploymentManifest
    created_at: datetime

    @classmethod
    def create(cls, *, code_digest: str, manifest: DeploymentManifest) -> "Revision":
        if len(code_digest) != 64:
            raise ValueError("code_digest must be a SHA-256 digest")
        int(code_digest, 16)
        identity = uuid5(
            NAMESPACE_URL,
            f"openrath-revision:{code_digest}:{manifest.canonical_json()}",
        )
        return cls(identity, code_digest, manifest, datetime.now(timezone.utc))

    @property
    def content_digest(self) -> str:
        """SHA-256 identity covering executable code and deployment manifest."""

        payload = json.dumps(
            {
                "code_digest": self.code_digest,
                "manifest": json.loads(self.manifest.canonical_json()),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@runtime_checkable
class RevisionStore(Protocol):
    def put(self, revision: Revision) -> Revision: ...

    def get(self, revision_id: UUID) -> Revision: ...


def _manifest(value: str | Mapping[str, Any]) -> DeploymentManifest:
    data = json.loads(value) if isinstance(value, str) else value
    return DeploymentManifest(
        image_digest=data["image_digest"],
        plan_hash=data["plan_hash"],
        python_version=data["python_version"],
        dependencies_digest=data["dependencies_digest"],
        resources=data["resources"],
    )


class SQLiteRevisionStore:
    def __init__(self, run_store: SQLiteRunStore) -> None:
        self.path = str(run_store.path)

    def put(self, revision: Revision) -> Revision:
        with sqlite3.connect(self.path) as connection:
            existing = connection.execute(
                "SELECT * FROM revisions WHERE id = ?", (str(revision.id),)
            ).fetchone()
            if existing is not None:
                loaded = self.get(revision.id)
                if (
                    loaded.code_digest != revision.code_digest
                    or loaded.manifest != revision.manifest
                ):
                    raise RevisionConflict("revision identity is immutable")
                return loaded
            connection.execute(
                """
                INSERT INTO revisions(
                    id, content_digest, code_digest, plan_hash,
                    manifest_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(revision.id),
                    revision.content_digest,
                    revision.code_digest,
                    revision.manifest.plan_hash,
                    revision.manifest.canonical_json(),
                    revision.created_at.isoformat(),
                ),
            )
        return revision

    def get(self, revision_id: UUID) -> Revision:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                "SELECT * FROM revisions WHERE id = ?", (str(revision_id),)
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise KeyError(str(revision_id))
        return Revision(
            id=UUID(row["id"]),
            code_digest=row["code_digest"],
            manifest=_manifest(row["manifest_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )


class PostgresRevisionStore:
    def __init__(self, run_store: PostgresRunStore) -> None:
        self.run_store = run_store

    def put(self, revision: Revision) -> Revision:
        from psycopg.types.json import Jsonb

        manifest = json.loads(revision.manifest.canonical_json())
        with self.run_store.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO revisions(
                    id, content_digest, code_digest, plan_hash,
                    manifest_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING RETURNING id
                """,
                (
                    revision.id,
                    revision.content_digest,
                    revision.code_digest,
                    revision.manifest.plan_hash,
                    Jsonb(manifest),
                    revision.created_at,
                ),
            ).fetchone()
        if row is None:
            loaded = self.get(revision.id)
            if (
                loaded.code_digest != revision.code_digest
                or loaded.manifest != revision.manifest
            ):
                raise RevisionConflict("revision identity is immutable")
            return loaded
        return revision

    def get(self, revision_id: UUID) -> Revision:
        with self.run_store.connection() as connection:
            row = connection.execute(
                "SELECT * FROM revisions WHERE id = %s", (revision_id,)
            ).fetchone()
        if row is None:
            raise KeyError(str(revision_id))
        return Revision(
            id=row["id"],
            code_digest=row["code_digest"],
            manifest=_manifest(row["manifest_json"]),
            created_at=row["created_at"],
        )
