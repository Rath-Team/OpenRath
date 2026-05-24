"""Lifecycle (open/close/store_count) tests for :class:`LocalMemoryBackend`.

Real filesystem only — no mocks. Each test gets an isolated ``OPENRATH_HOME``
so allocated store directories live under ``tmp_path``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest

from rath.memory import MemoryStore, MemoryStoreSpec
from rath.memory.adapters.local import LocalMemoryBackend
from rath.memory.capabilities import ScopeModel
from rath.memory.persistence import local_memory_root


@pytest.fixture(autouse=True)
def _isolate_openrath_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[Path]:
    target = tmp_path / "openrath_home"
    monkeypatch.setenv("OPENRATH_HOME", str(target))
    yield target


def test_is_available_returns_true() -> None:
    assert LocalMemoryBackend.is_available() is True


def test_capabilities_describe_fs_local_backend() -> None:
    caps = LocalMemoryBackend.capabilities()
    assert caps.scope_model in (ScopeModel.FS, ScopeModel.HYBRID)
    assert caps.supports_write
    assert caps.supports_read
    assert caps.supports_list
    assert caps.supports_tree
    assert caps.supports_resource_ingest
    assert caps.supports_session_commit


def test_open_without_spec_allocates_uuid_dir() -> None:
    backend = LocalMemoryBackend()
    store = backend.open()
    try:
        assert isinstance(store, MemoryStore)
        assert store.handle  # non-empty
        assert store.closed is False
        assert backend.store_count() == 1
        # Allocated under local_memory_root()/<uuid>/
        store_path = Path(store.handle)
        assert store_path.is_dir()
        assert store_path.parent == local_memory_root().resolve()
    finally:
        backend.close(store)


def test_open_with_explicit_path_uses_it() -> None:
    backend = LocalMemoryBackend()
    custom = local_memory_root().parent / "custom_store"
    spec = MemoryStoreSpec(options={"path": str(custom)})
    store = backend.open(spec)
    try:
        assert Path(store.handle) == custom.resolve()
        assert custom.is_dir()
    finally:
        backend.close(store)


def test_open_writes_meta_json_with_schema(_isolate_openrath_home: Path) -> None:
    backend = LocalMemoryBackend()
    store = backend.open()
    try:
        meta_path = Path(store.handle) / "meta.json"
        assert meta_path.is_file()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert "schema_version" in meta
        assert "created_at" in meta
        assert "last_used_at" in meta
    finally:
        backend.close(store)


def test_store_count_tracks_multiple_opens() -> None:
    backend = LocalMemoryBackend()
    s1 = backend.open()
    s2 = backend.open()
    try:
        assert s1.handle != s2.handle
        assert backend.store_count() == 2
    finally:
        backend.close(s1)
        backend.close(s2)
    assert backend.store_count() == 0


def test_close_marks_store_closed_and_decrements_count() -> None:
    backend = LocalMemoryBackend()
    store = backend.open()
    assert backend.store_count() == 1
    backend.close(store)
    assert store.closed is True
    assert backend.store_count() == 0


def test_close_is_idempotent() -> None:
    backend = LocalMemoryBackend()
    store = backend.open()
    backend.close(store)
    backend.close(store)  # must not raise
    assert store.closed is True
    assert backend.store_count() == 0


def test_close_does_not_delete_store_dir() -> None:
    """Persistence: closing a store leaves the on-disk directory behind."""
    backend = LocalMemoryBackend()
    store = backend.open()
    path = Path(store.handle)
    backend.close(store)
    assert path.is_dir(), "close() must not delete the persisted store"


def test_reopen_same_path_keeps_data() -> None:
    backend = LocalMemoryBackend()
    store = backend.open()
    path = Path(store.handle)
    (path / "marker.txt").write_text("hello", encoding="utf-8")
    backend.close(store)

    spec = MemoryStoreSpec(options={"path": str(path)})
    again = backend.open(spec)
    try:
        assert (Path(again.handle) / "marker.txt").read_text(
            encoding="utf-8"
        ) == "hello"
    finally:
        backend.close(again)


def test_backend_is_registered_under_local() -> None:
    from rath.memory import get_class

    assert get_class("local") is LocalMemoryBackend
