"""The IPython startup file that keeps OpenSandbox code runs from stalling.

These tests need neither the OpenSandbox SDK nor a server, so they run in the
fast test job.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import types
from types import SimpleNamespace

import pytest

import rath.backend.opensandbox as opensandbox_adapter
from rath.backend.opensandbox import (
    _KERNEL_WAKEUP_FILE,
    _KERNEL_WAKEUP_STARTUP,
    OpenSandboxBackend,
    _kernel_wakeup_command,
)


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


def test_kernel_wakeup_leaves_a_renamed_send_alone(monkeypatch) -> None:
    manager_cls = _fake_subshell_manager(monkeypatch, [])
    del manager_cls._send_on_shell_channel
    stream = _FakeShellStream()

    exec(
        _KERNEL_WAKEUP_STARTUP,
        {
            "get_ipython": lambda: SimpleNamespace(
                kernel=SimpleNamespace(shell_stream=stream)
            )
        },
    )

    assert not hasattr(manager_cls, "_send_on_shell_channel")


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
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
