"""Backend persistence: PersistentSandboxRegistry registry + GC operations.

Consolidated from (every test function name preserved verbatim):
- test_registry.py      (alloc / ensure / list / record_remote / load_remote / touch / list_remote)
- test_gc.py            (delete_local / prune_local / delete_remote / prune_remote / reattach errors)
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from rath.backend.abc import BackendSandboxSpec
from rath.backend.persistence import (
    PersistentSandboxRegistry,
    local_root,
    local_sandbox_dir,
    opensandbox_index_path,
    opensandbox_root,
)

# ---------------------------------------------------------------------------
# alloc / ensure / list / record_remote
# ---------------------------------------------------------------------------


def test_alloc_local_id_creates_directory(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    sid = reg.alloc_local_id()
    assert isinstance(sid, UUID)
    path = reg.local_path(sid)
    assert path == local_sandbox_dir(sid)
    assert path.is_dir()


def test_alloc_local_id_unique_per_call(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    a = reg.alloc_local_id()
    b = reg.alloc_local_id()
    assert a != b
    assert reg.local_path(a) != reg.local_path(b)


def test_ensure_local_idempotent(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    sid = uuid4()
    first = reg.ensure_local(sid)
    second = reg.ensure_local(sid)
    assert first == second
    assert first.is_dir()


@pytest.mark.parametrize("bad_id", ["../escape", "/tmp/escape", "not-a-uuid"])
def test_sandbox_paths_reject_path_like_ids(
    _isolate_openrath_home: Path,
    bad_id: str,
) -> None:
    with pytest.raises(ValueError, match="sandbox_id must be a UUID"):
        local_sandbox_dir(bad_id)
    with pytest.raises(ValueError, match="sandbox_id must be a UUID"):
        opensandbox_index_path(bad_id)


def test_list_local_enumerates_uuid_dirs(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    ids = {reg.alloc_local_id() for _ in range(3)}
    # Drop a non-UUID directory; it must be ignored.
    (local_root() / "garbage").mkdir(parents=True)
    listed = set(reg.list_local())
    assert listed == ids


def test_list_local_empty_when_dir_missing(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    assert reg.list_local() == []


def test_record_remote_writes_index_file(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    spec = BackendSandboxSpec(
        image="opensandbox/code-interpreter:v1.0.2",
        env={"FOO": "bar"},
        timeout=timedelta(seconds=600),
        working_dir="/workspace",
    )
    sid = reg.record_remote("opensandbox", "remote-id-xyz", spec)
    path = opensandbox_index_path(sid)
    assert path.is_file()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["backend"] == "opensandbox"
    assert raw["remote_id"] == "remote-id-xyz"
    assert raw["spec"]["working_dir"] == "/workspace"
    assert raw["spec"]["timeout_seconds"] == 600.0


def test_load_remote_round_trips_spec(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    spec = BackendSandboxSpec(working_dir="/ws", env={"K": "V"})
    sid = reg.record_remote("opensandbox", "rid-1", spec)
    rec = reg.load_remote(sid)
    assert rec is not None
    assert rec.backend == "opensandbox"
    assert rec.remote_id == "rid-1"
    assert rec.spec is not None
    assert rec.spec.working_dir == "/ws"
    assert rec.spec.env == {"K": "V"}


def test_load_remote_missing_returns_none(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    assert reg.load_remote(uuid4()) is None


def test_touch_remote_updates_last_used(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    sid = reg.record_remote("opensandbox", "rid-2", None)
    first = reg.load_remote(sid)
    assert first is not None
    time.sleep(0.005)
    reg.touch_remote(sid)
    second = reg.load_remote(sid)
    assert second is not None
    assert second.last_used_at >= first.last_used_at
    assert second.created_at == first.created_at


def test_list_remote_orders_by_created_at(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    a = reg.record_remote("opensandbox", "rid-a", None)
    time.sleep(0.005)
    b = reg.record_remote("opensandbox", "rid-b", None)
    rows = reg.list_remote()
    assert [r.id for r in rows] == [a, b]


def test_ensure_dirs_creates_both_roots(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    reg.ensure_dirs()
    assert local_root().is_dir()
    assert opensandbox_root().is_dir()


# ---------------------------------------------------------------------------
# GC: delete_local / prune_local / delete_remote / prune_remote / reattach errors
# ---------------------------------------------------------------------------


def test_delete_local_removes_dir(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    sid = reg.alloc_local_id()
    assert reg.local_path(sid).is_dir()
    assert reg.delete_local(sid) is True
    assert not reg.local_path(sid).exists()


def test_delete_local_returns_false_when_absent(
    _isolate_openrath_home: Path,
) -> None:
    reg = PersistentSandboxRegistry()
    assert reg.delete_local(uuid4()) is False


def test_delete_local_removes_with_contents(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    sid = reg.alloc_local_id()
    (reg.local_path(sid) / "nested" / "deep").mkdir(parents=True)
    (reg.local_path(sid) / "nested" / "file.txt").write_text("x", encoding="utf-8")
    assert reg.delete_local(sid) is True
    assert not reg.local_path(sid).exists()


def test_prune_local_removes_only_old_dirs(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    old = reg.alloc_local_id()
    new = reg.alloc_local_id()
    # Backdate the old dir's mtime by a year.
    old_path = local_sandbox_dir(old)
    ancient = time.time() - 365 * 24 * 3600
    os.utime(old_path, (ancient, ancient))

    removed = reg.prune_local(older_than=timedelta(days=30))
    assert removed == [old]
    assert not old_path.exists()
    assert reg.local_path(new).is_dir()


def test_prune_local_empty_when_no_old_dirs(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    reg.alloc_local_id()
    assert reg.prune_local(older_than=timedelta(days=30)) == []


def test_delete_remote_removes_index(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    sid = reg.record_remote("opensandbox", "remote-1", None)
    assert opensandbox_index_path(sid).is_file()
    assert reg.delete_remote(sid) is True
    assert not opensandbox_index_path(sid).exists()


def test_delete_remote_returns_false_when_absent(
    _isolate_openrath_home: Path,
) -> None:
    reg = PersistentSandboxRegistry()
    assert reg.delete_remote(uuid4()) is False


def test_prune_remote_uses_last_used_at(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    sid_old = reg.record_remote("opensandbox", "rid-old", None)
    sid_new = reg.record_remote("opensandbox", "rid-new", None)

    # Rewrite the old record's last_used_at to long ago.
    path = opensandbox_index_path(sid_old)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["last_used_at"] = (
        datetime.now(timezone.utc) - timedelta(days=400)
    ).isoformat()
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    removed = reg.prune_remote(older_than=timedelta(days=30))
    assert removed == [sid_old]
    assert reg.load_remote(sid_new) is not None


def test_reattach_remote_missing_id_raises(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    with pytest.raises(KeyError, match="no remote sandbox"):
        reg.reattach_remote(uuid4())


def test_reattach_remote_unsupported_backend_raises(
    _isolate_openrath_home: Path,
) -> None:
    reg = PersistentSandboxRegistry()
    # ``local`` backend has no ``attach`` method.
    sid = reg.record_remote(
        "local", "rid-not-supported", BackendSandboxSpec(working_dir="/tmp/x")
    )
    with pytest.raises(AttributeError, match="does not support reattach"):
        reg.reattach_remote(sid)
