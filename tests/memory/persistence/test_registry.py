"""Real-fs tests for :class:`PersistentMemoryRegistry`.

Mirrors :mod:`tests.backends.persistence.test_registry` (local half only —
no remote records yet for the memory plane).
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

from rath.memory.persistence import (
    PersistentMemoryRegistry,
    local_memory_root,
    local_store_dir,
)


def test_alloc_local_id_creates_directory(_isolate_openrath_home: Path) -> None:
    reg = PersistentMemoryRegistry()
    sid = reg.alloc_local_id()
    assert isinstance(sid, UUID)
    path = reg.local_path(sid)
    assert path == local_store_dir(sid)
    assert path.is_dir()


def test_alloc_local_id_unique_per_call(_isolate_openrath_home: Path) -> None:
    reg = PersistentMemoryRegistry()
    a = reg.alloc_local_id()
    b = reg.alloc_local_id()
    assert a != b
    assert reg.local_path(a) != reg.local_path(b)


def test_ensure_local_idempotent(_isolate_openrath_home: Path) -> None:
    reg = PersistentMemoryRegistry()
    sid = uuid4()
    first = reg.ensure_local(sid)
    second = reg.ensure_local(sid)
    assert first == second
    assert first.is_dir()


def test_list_local_enumerates_uuid_dirs(_isolate_openrath_home: Path) -> None:
    reg = PersistentMemoryRegistry()
    ids = {reg.alloc_local_id() for _ in range(3)}
    # Drop a non-UUID directory; it must be ignored.
    (local_memory_root() / "garbage").mkdir(parents=True)
    listed = set(reg.list_local())
    assert listed == ids


def test_list_local_empty_when_dir_missing(_isolate_openrath_home: Path) -> None:
    reg = PersistentMemoryRegistry()
    assert reg.list_local() == []


def test_delete_local_removes_directory(_isolate_openrath_home: Path) -> None:
    reg = PersistentMemoryRegistry()
    sid = reg.alloc_local_id()
    path = reg.local_path(sid)
    # Drop a file inside; rmtree must clean it up.
    (path / "user").mkdir()
    (path / "user" / "notes.md").write_text("hello", encoding="utf-8")

    assert reg.delete_local(sid) is True
    assert not path.exists()
    # Second call is a no-op.
    assert reg.delete_local(sid) is False


def test_prune_local_removes_old_stores(_isolate_openrath_home: Path) -> None:
    import os
    import time

    reg = PersistentMemoryRegistry()
    fresh = reg.alloc_local_id()
    stale = reg.alloc_local_id()

    # Backdate ``stale``'s mtime by 60 days.
    stale_path = reg.local_path(stale)
    backdated = time.time() - timedelta(days=60).total_seconds()
    os.utime(stale_path, (backdated, backdated))

    removed = reg.prune_local(older_than=timedelta(days=30))
    assert removed == [stale]
    assert reg.local_path(fresh).is_dir()
    assert not stale_path.exists()
