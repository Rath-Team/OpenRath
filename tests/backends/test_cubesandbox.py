"""Adapter-level tests for ``CubeSandboxBackend`` (no live server)."""

from __future__ import annotations

import pytest

from rath.backend import (
    BackendToolCodeRun,
    BackendToolCommandRun,
    BackendToolFilesExists,
    BackendToolFilesList,
    BackendToolFilesRead,
    BackendToolFilesWrite,
    Capabilities,
    IsolationLevel,
    get,
)
from rath.backend.cubesandbox import CubeSandboxBackend


def test_registered_under_name_cubesandbox() -> None:
    inst = get("cubesandbox")
    assert isinstance(inst, CubeSandboxBackend)
    assert inst.name == "cubesandbox"


def test_capabilities_describe_microvm() -> None:
    cap = CubeSandboxBackend.capabilities()
    assert isinstance(cap, Capabilities)
    assert cap.isolation is IsolationLevel.MICROVM
    assert cap.supports_command is True
    assert cap.supports_filesystem is True
    assert cap.supports_code_interpreter is True
    assert cap.cold_start_ms_p50 == 60


def test_supported_calls_covers_all_phase1_types() -> None:
    assert CubeSandboxBackend.supported_calls() == frozenset(
        {
            BackendToolCommandRun,
            BackendToolFilesRead,
            BackendToolFilesWrite,
            BackendToolFilesList,
            BackendToolFilesExists,
            BackendToolCodeRun,
        }
    )


def test_is_available_requires_sdk_and_template(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.delitem(sys.modules, "e2b_code_interpreter", raising=False)
    monkeypatch.delenv("CUBE_TEMPLATE_ID", raising=False)
    monkeypatch.delenv("RATH_CUBESANDBOX_TEMPLATE_ID", raising=False)
    assert CubeSandboxBackend.is_available() is False


import sys
import types

from tests.backends._fake_e2b import FakeSandbox


@pytest.fixture
def fake_sdk(monkeypatch: pytest.MonkeyPatch) -> type[FakeSandbox]:
    """Install a stub ``e2b_code_interpreter`` module exposing ``FakeSandbox``."""

    module = types.ModuleType("e2b_code_interpreter")
    module.Sandbox = FakeSandbox  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "e2b_code_interpreter", module)
    # The adapter already imported ``_E2BSandbox`` at module load time, so
    # patch the bound reference directly.
    import rath.backend.cubesandbox as adapter_mod

    monkeypatch.setattr(adapter_mod, "_E2BSandbox", FakeSandbox, raising=False)
    monkeypatch.setattr(adapter_mod, "_SDK_AVAILABLE", True, raising=False)
    monkeypatch.setenv("CUBE_TEMPLATE_ID", "tpl-test")
    return FakeSandbox


def test_open_returns_handle_and_increments_count(
    fake_sdk: type[FakeSandbox],
) -> None:
    backend = get("cubesandbox")
    sb = backend.open()
    try:
        assert backend.sandbox_count() == 1
        assert sb.handle.startswith("fake-")
    finally:
        backend.close(sb)
    assert backend.sandbox_count() == 0


def test_close_calls_kill_exactly_once(fake_sdk: type[FakeSandbox]) -> None:
    backend = get("cubesandbox")
    sb = backend.open()
    native = backend._natives[sb.handle]  # type: ignore[attr-defined]
    backend.close(sb)
    backend.close(sb)  # idempotent
    assert native.kill_count == 1


def test_attach_reuses_remote_id(fake_sdk: type[FakeSandbox]) -> None:
    backend = get("cubesandbox")
    sb = backend.attach("tpl-remote-123")  # type: ignore[attr-defined]
    try:
        assert sb.handle == "tpl-remote-123"
    finally:
        backend.close(sb)


from rath.backend import (
    CommandResult,
    FileContent,
    FileEntries,
    FileWriteResult,
    ToolExecutionFailure,
)


def test_command_run_returns_command_result(fake_sdk: type[FakeSandbox]) -> None:
    backend = get("cubesandbox")
    with backend.open() as sb:
        r = sb.dispatch(BackendToolCommandRun(cmd=["echo", "hi"]))
    assert isinstance(r, CommandResult)
    assert r.exit_code == 0
    assert r.stdout == b"ok\n"


def test_command_run_stdin_rejected(fake_sdk: type[FakeSandbox]) -> None:
    backend = get("cubesandbox")
    with backend.open() as sb:
        r = sb.dispatch(BackendToolCommandRun(cmd=["cat"], stdin=b"x"))
    assert isinstance(r, ToolExecutionFailure)
    assert r.kind == "unsupported_tool"


def test_files_write_read_roundtrip(fake_sdk: type[FakeSandbox]) -> None:
    backend = get("cubesandbox")
    with backend.open() as sb:
        w = sb.dispatch(BackendToolFilesWrite(path="hello.txt", data="world"))
        assert isinstance(w, FileWriteResult)
        assert w.bytes_written == 5
        r = sb.dispatch(BackendToolFilesRead(path="hello.txt"))
    assert isinstance(r, FileContent)
    assert r.data == "world"


def test_files_list_returns_sorted_entries(fake_sdk: type[FakeSandbox]) -> None:
    backend = get("cubesandbox")
    with backend.open() as sb:
        sb.dispatch(BackendToolFilesWrite(path="b.txt", data="2"))
        sb.dispatch(BackendToolFilesWrite(path="a.txt", data="1"))
        listing = sb.dispatch(BackendToolFilesList(path="."))
    assert isinstance(listing, FileEntries)
    assert [e.name for e in listing.entries] == ["a.txt", "b.txt"]


def test_files_exists_returns_bool(fake_sdk: type[FakeSandbox]) -> None:
    backend = get("cubesandbox")
    with backend.open() as sb:
        sb.dispatch(BackendToolFilesWrite(path="present.txt", data="x"))
        present = sb.dispatch(BackendToolFilesExists(path="present.txt"))
        missing = sb.dispatch(BackendToolFilesExists(path="missing.txt"))
    assert present is True
    assert missing is False
