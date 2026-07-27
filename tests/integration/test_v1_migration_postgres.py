from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from rath.runtime import PostgresRunStore, RunStatus
from rath.session import Session
from rath.session.chunk import ChunkTable
from rath.session.persistence.writer import SessionWriter

pytestmark = pytest.mark.skipif(
    not os.getenv("OPENRATH_TEST_POSTGRES_DSN"),
    reason="OPENRATH_TEST_POSTGRES_DSN is not configured",
)


def test_v1_session_import_real_postgres(tmp_path: Path) -> None:
    dsn = os.environ["OPENRATH_TEST_POSTGRES_DSN"]
    schema = f"migration_{uuid4().hex}"
    source = tmp_path / "sessions"
    source.mkdir()
    session = Session(chunk_table=ChunkTable(rows=()))
    SessionWriter(session, path=source / f"{session.id}.jsonl").close()
    report = tmp_path / "result.json"
    artifact_root = tmp_path / "artifacts"
    try:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/migrate_v1_to_v2.py",
                "--source",
                str(source),
                "--report",
                str(report),
                "--tenant",
                "migration-tenant",
                "--apply",
                "--postgres-dsn",
                dsn,
                "--schema",
                schema,
                "--artifact-root",
                str(artifact_root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["summary"]["imported"] == 1
        store = PostgresRunStore(dsn, schema=schema)
        runs = store.list_runs(tenant_id="migration-tenant")
        assert len(runs) == 1
        assert runs[0].status is RunStatus.SUCCEEDED
        assert runs[0].state["resumable"] is False
        store.close()
    finally:
        import psycopg
        from psycopg import sql

        with psycopg.connect(dsn) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    sql.Identifier(schema)
                )
            )
