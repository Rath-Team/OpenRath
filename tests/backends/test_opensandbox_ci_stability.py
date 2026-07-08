"""Offline guards for OpenSandbox CI stability (no live server required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from rath.backend.opensandbox import (
    _is_transient_sandbox_create_error,
    _should_retry_command_for_empty_stdout,
)

pytest.importorskip("opensandbox")
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


def test_transient_create_error_rejects_bind_rejection() -> None:
    exc = ValueError("host path not under any allowed prefix")
    assert not _is_transient_sandbox_create_error(exc)
