from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from rath.session import Session
from rath.session.chunk import ChunkTable
from rath.session.persistence.writer import SessionWriter


def test_v1_migration_inventory_is_read_only_and_machine_readable(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sessions"
    source.mkdir()
    session = Session(chunk_table=ChunkTable(rows=()))
    legacy_path = source / f"{session.id}.jsonl"
    SessionWriter(session, path=legacy_path).close()
    before = legacy_path.read_bytes()
    report = tmp_path / "inventory.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/migrate_v1_to_v2.py",
            "--source",
            str(source),
            "--report",
            str(report),
            "--tenant",
            "tenant-1",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert legacy_path.read_bytes() == before
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["mode"] == "inventory"
    assert payload["summary"] == {
        "total": 1,
        "ready": 1,
        "imported": 0,
        "invalid": 0,
    }
