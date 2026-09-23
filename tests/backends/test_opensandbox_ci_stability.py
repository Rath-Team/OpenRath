"""Offline guards for OpenSandbox CI stability (no live server required)."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

import rath.backend.opensandbox as opensandbox_adapter
from rath.backend.opensandbox import (
    _KERNEL_WAKEUP_FILE,
    _KERNEL_WAKEUP_STARTUP,
    OpenSandboxBackend,
    _command_stdout_rerun_allowed,
    _is_transient_code_run_result,
    _is_transient_sandbox_create_error,
    _kernel_wakeup_command,
    _run_code_with_retry,
    _should_retry_command_for_empty_stdout,
)

pytest.importorskip("opensandbox")
from code_interpreter import CodeInterpreter  # noqa: E402
from opensandbox.exceptions import SandboxInternalException  # noqa: E402
from opensandbox.models.execd import (  # noqa: E402
    Execution,
    ExecutionComplete,
    ExecutionLogs,
    OutputMessage,
)


def test_ci_prepull_image_matches_backend_default() -> None:
    workflow = Path(".github/workflows/ci-test-opensandbox.yml").read_text(
        encoding="utf-8"
    )
    assert "OpenSandboxBackend._DEFAULT_IMAGE" in workflow
    assert "opensandbox/code-interpreter:v1.0.2" not in workflow
    assert "--reruns" not in workflow


def test_should_retry_empty_stdout_race() -> None:
    execution = Execution(
        complete=ExecutionComplete(timestamp=1, execution_time_in_millis=5),
        exit_code=0,
    )
    assert _should_retry_command_for_empty_stdout(execution)


def test_should_not_retry_when_stdout_present() -> None:
    execution = Execution(
        complete=ExecutionComplete(timestamp=1, execution_time_in_millis=5),
        exit_code=0,
        logs=ExecutionLogs(stdout=[OutputMessage(text="hello\n", timestamp=1)]),
    )
    assert not _should_retry_command_for_empty_stdout(execution)


def test_should_not_retry_nonzero_exit() -> None:
    execution = Execution(
        complete=ExecutionComplete(timestamp=1, execution_time_in_millis=5),
        exit_code=7,
    )
    assert not _should_retry_command_for_empty_stdout(execution)


def test_transient_create_error_detects_network_timeout() -> None:
    exc = SandboxInternalException(
        "Network connectivity error:",
        cause=TimeoutError("read timed out"),
    )
    assert _is_transient_sandbox_create_error(exc)


def test_command_stdout_rerun_limited_to_print_probes() -> None:
    assert _command_stdout_rerun_allowed("python3 -c \"print('hello')\"")
    assert not _command_stdout_rerun_allowed(
        "python3 -c \"pathlib.Path('x').write_text('y')\""
    )


def test_transient_code_run_detects_busy_session() -> None:
    execution = SimpleNamespace(
        error=SimpleNamespace(value="error running codes session is busy")
    )
    assert _is_transient_code_run_result(execution)


def test_transient_code_run_ignores_real_failures() -> None:
    execution = SimpleNamespace(
        error=SimpleNamespace(value="SyntaxError: invalid syntax"),
    )
    assert not _is_transient_code_run_result(execution)


def test_busy_result_after_client_timeout_stays_a_timeout(monkeypatch) -> None:
    calls = 0
    busy = SimpleNamespace(
        error=SimpleNamespace(value="error running codes session is busy")
    )

    class FakeCodes:
        async def run(self, source, *, language):  # type: ignore[no-untyped-def]
            return None

    async def fake_create(native):  # type: ignore[no-untyped-def]
        return SimpleNamespace(codes=FakeCodes())

    async def fake_await(awaitable, timeout):  # type: ignore[no-untyped-def]
        nonlocal calls
        await awaitable
        calls += 1
        if calls == 1:
            raise TimeoutError("client deadline")
        return busy

    monkeypatch.setattr(CodeInterpreter, "create", staticmethod(fake_create))
    monkeypatch.setattr(opensandbox_adapter, "_await_maybe_timeout", fake_await)
    monkeypatch.setattr(opensandbox_adapter, "_CODE_RUN_BACKOFF_S", (0.0,))

    with pytest.raises(TimeoutError, match="remained busy after timeout"):
        asyncio.run(_run_code_with_retry(object(), "pass", "python", 0.5))


def test_transient_create_error_rejects_bind_rejection() -> None:
    exc = ValueError("host path not under any allowed prefix")
    assert not _is_transient_sandbox_create_error(exc)


class _FakeShellStream:
    def __init__(self) -> None:
        self.rearmed = 0

    def _rebuild_io_state(self) -> None:
        self.rearmed += 1


def _fake_subshell_manager(monkeypatch, sent: list) -> type:
    class SubshellManager:
        def _send_on_shell_channel(self, msg) -> None:  # type: ignore[no-untyped-def]
            sent.append(msg)

    package = types.ModuleType("ipykernel")
    module = types.ModuleType("ipykernel.subshell_manager")
    module.SubshellManager = SubshellManager  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ipykernel", package)
    monkeypatch.setitem(sys.modules, "ipykernel.subshell_manager", module)
    return SubshellManager


def test_kernel_wakeup_rearms_shell_stream_after_each_raw_reply(monkeypatch) -> None:
    """The startup file makes every raw shell reply re-read the stream's events.

    Without that, a request landing during the raw send stays unread in the
    kernel's shell socket (ipython/ipykernel#1554) and the code run never ends.
    Running the file twice must not wrap the send twice.
    """
    sent: list = []
    manager_cls = _fake_subshell_manager(monkeypatch, sent)
    stream = _FakeShellStream()
    user_ns = {
        "get_ipython": lambda: SimpleNamespace(
            kernel=SimpleNamespace(shell_stream=stream)
        )
    }

    exec(_KERNEL_WAKEUP_STARTUP, user_ns)
    exec(_KERNEL_WAKEUP_STARTUP, user_ns)
    manager_cls()._send_on_shell_channel([b"reply"])

    assert sent == [[b"reply"]]
    assert stream.rearmed == 1
    assert "_openrath_rearm_shell_stream" not in user_ns


def test_kernel_wakeup_leaves_kernels_without_subshells_alone(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "ipykernel.subshell_manager", None)
    exec(_KERNEL_WAKEUP_STARTUP, {"get_ipython": lambda: None})


@pytest.mark.parametrize("ipythondir", [None, "custom-ipython"])
def test_kernel_wakeup_command_writes_the_startup_file(tmp_path, ipythondir) -> None:
    env = {k: v for k, v in os.environ.items() if k != "IPYTHONDIR"}
    env["HOME"] = str(tmp_path)
    base = tmp_path / ".ipython"
    if ipythondir is not None:
        base = tmp_path / ipythondir
        env["IPYTHONDIR"] = str(base)

    subprocess.run(["bash", "-c", _kernel_wakeup_command()], env=env, check=True)

    startup = base / "profile_default" / "startup" / _KERNEL_WAKEUP_FILE
    assert startup.read_text(encoding="utf-8") == _KERNEL_WAKEUP_STARTUP


@pytest.mark.parametrize("volumes", [None, ["bound"]])
def test_open_installs_kernel_wakeup_before_any_code_runs(monkeypatch, volumes) -> None:
    ran: list[str] = []

    class FakeCommands:
        async def run(self, command, **kwargs):  # type: ignore[no-untyped-def]
            ran.append(command)

    native = SimpleNamespace(id="sbx-1", commands=FakeCommands())

    async def fake_create(image, timeout, env, entrypoint, requested):  # type: ignore[no-untyped-def]
        return native, volumes

    monkeypatch.setattr(
        opensandbox_adapter, "_create_sandbox_with_optional_bind_fallback", fake_create
    )
    backend = OpenSandboxBackend()

    asyncio.run(
        backend._open_coro(
            "image", opensandbox_adapter._CREATE_REQUEST_TIMEOUT, None, [], None
        )
    )

    assert len(ran) == 1
    assert _kernel_wakeup_command() in ran[0]
    mkdir = f"mkdir -p {OpenSandboxBackend._SANDBOX_ROOT}"
    assert (mkdir in ran[0]) == (volumes is None)
