"""Memory-plane persistence: path resolution + PersistentMemoryRegistry.

Consolidated from (every test function name preserved verbatim):
- test_paths.py         (memory_root / local_memory_root / local_store_dir layout)
- test_registry.py      (PersistentMemoryRegistry alloc / ensure / list / delete / prune)
"""

from __future__ import annotations

import os
import time
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from rath.memory.persistence import (
    PersistentMemoryRegistry,
    local_memory_root,
    local_store_dir,
)
from rath.memory.persistence.paths import (
    LOCAL_SUBDIR,
    MEMORY_DIR_NAME,
    ensure_local_memory_root,
    memory_root,
)

# ---------------------------------------------------------------------------
# path resolution
# ---------------------------------------------------------------------------


def test_memory_root_under_openrath_home(_isolate_openrath_home: Path) -> None:
    root = memory_root()
    assert root == _isolate_openrath_home.resolve() / MEMORY_DIR_NAME
    assert MEMORY_DIR_NAME == "memory"


def test_local_memory_root_is_memory_root_slash_local(
    _isolate_openrath_home: Path,
) -> None:
    assert local_memory_root() == memory_root() / LOCAL_SUBDIR
    assert LOCAL_SUBDIR == "local"


def test_local_store_dir_resolves_under_local_root(
    _isolate_openrath_home: Path,
) -> None:
    sid = uuid4()
    assert local_store_dir(sid) == local_memory_root() / str(sid)


def test_local_store_dir_accepts_str(_isolate_openrath_home: Path) -> None:
    """UUIDs may arrive as strings from JSON; both forms must resolve identically."""
    sid = uuid4()
    assert local_store_dir(str(sid)) == local_store_dir(sid)


@pytest.mark.parametrize("bad_id", ["../escape", "/tmp/escape", "not-a-uuid"])
def test_local_store_dir_rejects_path_like_ids(
    _isolate_openrath_home: Path,
    bad_id: str,
) -> None:
    with pytest.raises(ValueError, match="store_id must be a UUID"):
        local_store_dir(bad_id)


def test_ensure_local_memory_root_creates_and_is_idempotent(
    _isolate_openrath_home: Path,
) -> None:
    assert not local_memory_root().exists()
    first = ensure_local_memory_root()
    assert first.is_dir()
    second = ensure_local_memory_root()
    assert second == first
    assert second.is_dir()


def test_memory_root_lives_next_to_sandboxes(
    _isolate_openrath_home: Path,
) -> None:
    """Memory and sandboxes share a parent — the resolved ``.openrath/`` dir."""
    from rath.backend.persistence.paths import sandboxes_dir

    assert memory_root().parent == sandboxes_dir().parent


# ---------------------------------------------------------------------------
# PersistentMemoryRegistry
# ---------------------------------------------------------------------------


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
