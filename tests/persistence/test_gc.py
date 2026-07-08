"""P3.4 — unified retention/GC across all persistence planes.

Real filesystem. ``rath.persistence.gc`` enumerates prunable artifacts by age
across sessions, sandboxes (local dirs + remote index), memory stores, and —
critically — the previously-unbounded memory commits archive. dry_run reports
without deleting; a real run removes only what it reported. Never touches paths
outside the resolved data root.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from typing import Iterator

import pytest

from rath.persistence.gc import GCReport, gc


@pytest.fixture(autouse=True)
def _isolate_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    root = tmp_path / "openrath_home"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OPENRATH_HOME", str(root))
    yield root


def _age(path: Path, days: int) -> None:
    """Backdate a path's mtime by ``days`` days."""
    past = (Path(path).stat().st_mtime) - days * 86400
    os.utime(path, (past, past))


def test_gc_prunes_old_memory_commits(_isolate_home: Path) -> None:
    # Build a memory store with two commit archives, backdate one.
    store = _isolate_home / "memory" / "local" / "store1"
    old_commit = store / "session" / "s1" / "commits" / "20240101T000000000000"
    new_commit = store / "session" / "s1" / "commits" / "20260705T000000000000"
    for c in (old_commit, new_commit):
        c.mkdir(parents=True, exist_ok=True)
        (c / "messages.json").write_text("[]", encoding="utf-8")
    _age(old_commit, days=400)

    report = gc(older_than=timedelta(days=90), dry_run=True)
    assert isinstance(report, GCReport)
    assert str(old_commit) in [str(p) for p in report.memory_commits]
    assert str(new_commit) not in [str(p) for p in report.memory_commits]
    # dry-run must not delete.
    assert old_commit.exists()

    report2 = gc(older_than=timedelta(days=90), dry_run=False)
    assert not old_commit.exists()
    assert new_commit.exists()  # recent one kept
    assert str(old_commit) in [str(p) for p in report2.memory_commits]


def test_gc_dry_run_reports_all_categories(_isolate_home: Path) -> None:
    report = gc(older_than=timedelta(days=30), dry_run=True)
    # Report has a slot for each plane even when empty.
    assert report.sessions == []
    assert report.local_sandboxes == []
    assert report.remote_sandboxes == []
    assert report.memory_stores == []
    assert report.memory_commits == []


def test_gc_never_escapes_root(_isolate_home: Path) -> None:
    # A commit-like dir OUTSIDE the root must never be collected.
    outside = _isolate_home.parent / "outside" / "commits" / "20240101T000000000000"
    outside.mkdir(parents=True, exist_ok=True)
    _age(outside, days=999)
    report = gc(older_than=timedelta(days=1), dry_run=False)
    assert outside.exists()
    assert all(str(_isolate_home) in str(p) for p in report.memory_commits)
