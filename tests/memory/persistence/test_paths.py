"""Path-resolution tests for the memory-plane persistence layer.

Mirrors :mod:`tests.backends.persistence.test_paths`: the memory plane lives
under ``<openrath_home>/memory/`` parallel to ``sandboxes/`` so a user with
both planes active sees a clean two-folder layout.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from rath.memory.persistence.paths import (
    LOCAL_SUBDIR,
    MEMORY_DIR_NAME,
    ensure_local_memory_root,
    local_memory_root,
    local_store_dir,
    memory_root,
)


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
