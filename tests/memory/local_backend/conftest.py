"""Shared fixtures for LocalMemoryBackend tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from rath.memory import MemoryStore, MemoryStoreSpec
from rath.memory.adapters.local import LocalMemoryBackend


@pytest.fixture(autouse=True)
def _isolate_openrath_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[Path]:
    target = tmp_path / "openrath_home"
    monkeypatch.setenv("OPENRATH_HOME", str(target))
    yield target


@pytest.fixture
def backend() -> Iterator[LocalMemoryBackend]:
    b = LocalMemoryBackend()
    yield b
    # Drain any remaining stores so subsequent tests see a clean process.
    for handle in list(b._handles):  # type: ignore[attr-defined]
        b._handles.pop(handle)  # type: ignore[attr-defined]


@pytest.fixture
def store(
    backend: LocalMemoryBackend,
    tmp_path: Path,
) -> Iterator[MemoryStore]:
    spec = MemoryStoreSpec(
        options={
            "resource_import_roots": [str(tmp_path)],
            "resource_allowed_http_hosts": ["127.0.0.1"],
            "resource_allow_private_hosts": True,
        },
    )
    s = backend.open(spec)
    try:
        yield s
    finally:
        if not s.closed:
            backend.close(s)
