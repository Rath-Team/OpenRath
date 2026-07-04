"""OpenSandbox-only tests (``opensandbox_real``; reachable server on localhost).

Covers capabilities, ``is_available``, and command/file adapter paths."""

from __future__ import annotations

import pytest

from rath.backend import (
    BackendToolCodeRun,
    BackendToolCommandRun,
    BackendToolFilesExists,
    BackendToolFilesList,
    BackendToolFilesRead,
    BackendToolFilesWrite,
    CodeResult,
    CommandResult,
    FileContent,
    FileEntries,
    IsolationLevel,
    ToolExecutionFailure,
    get,
)
from rath.backend.opensandbox import OpenSandboxBackend
from tests.conftest import opensandbox_real

pytestmark = [opensandbox_real, pytest.mark.opensandbox]


def test_capabilities_match_spec() -> None:
    cap = OpenSandboxBackend.capabilities()
    assert cap.isolation is IsolationLevel.CONTAINER
    assert cap.supports_command is True
    assert cap.supports_filesystem is True
    assert cap.supports_code_interpreter is True


def test_supported_calls_covers_all_phase1_types() -> None:
    expected = {
        BackendToolCommandRun,
        BackendToolFilesRead,
        BackendToolFilesWrite,
        BackendToolFilesList,
        BackendToolFilesExists,
        BackendToolCodeRun,
    }
    assert OpenSandboxBackend.supported_calls() == expected


def test_registered_under_name_opensandbox() -> None:
    inst = get("opensandbox")
    assert isinstance(inst, OpenSandboxBackend)
    assert inst.name == "opensandbox"


def test_open_close_roundtrip() -> None:
    backend = get("opensandbox")
    sb = backend.open()
    try:
        assert backend.sandbox_count() == 1
        assert sb.handle != ""
    finally:
        backend.close(sb)
    assert backend.sandbox_count() == 0


def test_command_run_stdin_rejected() -> None:
    """OpenSandbox's commands.run has no stdin; adapter returns a structured failure."""
    backend = get("opensandbox")
    with backend.open() as sb:
        r = sb.dispatch(
            BackendToolCommandRun(cmd=["python3", "-c", "pass"], stdin=b"x")
        )
        assert isinstance(r, ToolExecutionFailure)
        assert r.kind == "unsupported_tool"


def test_files_list_returns_entries_with_metadata() -> None:
    """Adapter's ``files.search`` -> ``FileEntries`` mapping must be well-formed."""
    backend = get("opensandbox")
    with backend.open() as sb:
        sb.dispatch(BackendToolFilesWrite(path="/tmp/rath_a.txt", data="a"))
        sb.dispatch(BackendToolFilesWrite(path="/tmp/rath_b.txt", data="b"))
        result = sb.dispatch(BackendToolFilesList(path="/tmp"))
        assert isinstance(result, FileEntries)
        names = {e.name for e in result.entries}
        assert {"rath_a.txt", "rath_b.txt"}.issubset(names)


def test_files_exists_true_and_false() -> None:
    backend = get("opensandbox")
    with backend.open() as sb:
        sb.dispatch(BackendToolFilesWrite(path="/tmp/rath_present.txt", data="x"))
        assert sb.dispatch(BackendToolFilesExists(path="/tmp/rath_present.txt")) is True
        assert (
            sb.dispatch(BackendToolFilesExists(path="/tmp/rath_definitely_missing.txt"))
            is False
        )


def test_unsupported_language_returns_failure() -> None:
    backend = get("opensandbox")
    with backend.open() as sb:
        r = sb.dispatch(BackendToolCodeRun(code="puts 'hi'", language="ruby"))
        assert isinstance(r, ToolExecutionFailure)
        assert r.kind == "unsupported_tool"


@pytest.mark.timeout(600)
def test_code_run_python_round_trip() -> None:
    """Smoke that ``codes.run`` produces both stdout and a result text."""
    backend = get("opensandbox")
    with backend.open() as sb:
        result = sb.dispatch(BackendToolCodeRun(code="x = 1 + 1\nprint(x)\nx"))
        assert isinstance(result, CodeResult)
        assert result.error is None
        assert b"2" in result.stdout


def test_files_read_text_and_bytes() -> None:
    backend = get("opensandbox")
    with backend.open() as sb:
        sb.dispatch(BackendToolFilesWrite(path="/tmp/rath_rw.txt", data="hello"))
        text = sb.dispatch(BackendToolFilesRead(path="/tmp/rath_rw.txt"))
        assert isinstance(text, FileContent)
        assert text.data == "hello"
        raw = sb.dispatch(BackendToolFilesRead(path="/tmp/rath_rw.txt", encoding=None))
        assert isinstance(raw, FileContent)
        assert raw.data == b"hello"


def test_simple_command_run_exit_code_and_stdout() -> None:
    backend = get("opensandbox")
    with backend.open() as sb:
        result = sb.dispatch(
            BackendToolCommandRun(cmd=["python3", "-c", "print('hello')"])
        )
        assert isinstance(result, CommandResult)
        assert result.exit_code == 0
        assert b"hello" in result.stdout
