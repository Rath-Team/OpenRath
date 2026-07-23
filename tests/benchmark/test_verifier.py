from __future__ import annotations

import sys
from typing import Any

import pytest

import rath.benchmark.verifier as verifier_module
from rath.backend import CommandResult, ToolExecutionFailure
from rath.benchmark import (
    BenchmarkTask,
    CommandVerifier,
    PytestVerifier,
    VerifierExecutionError,
)
from rath.session import Session


def _task(verifier: Any) -> BenchmarkTask:
    return BenchmarkTask(
        task_id="task",
        name="Task",
        category="software",
        description="Fix it.",
        language="Python",
        metric="pass",
        verifier=verifier,
    )


def test_pytest_verifier_uses_sandbox_python_command() -> None:
    assert PytestVerifier().cmd == ["python", "-m", "pytest", "-q"]
    assert PytestVerifier(python_command="python3").cmd == [
        "python3",
        "-m",
        "pytest",
        "-q",
    ]
    assert sys.executable not in PytestVerifier().cmd


def test_nonzero_exit_is_verification_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = CommandVerifier(["python", "-m", "pytest", "-q"])
    monkeypatch.setattr(
        verifier_module,
        "flow_tool_command_run",
        lambda *args, **kwargs: CommandResult(1, b"", b"assert failed", 2.0),
    )
    result = verifier.verify(_task(verifier), Session.create("empty"))
    assert result.passed is False
    assert result.info["exit_code"] == 1


@pytest.mark.parametrize(
    "raw",
    [
        ToolExecutionFailure("timeout", "timed out", "TimeoutExpired"),
        object(),
    ],
)
def test_verifier_infrastructure_failure_raises(
    raw: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = CommandVerifier("pytest")
    monkeypatch.setattr(
        verifier_module, "flow_tool_command_run", lambda *args, **kwargs: raw
    )
    with pytest.raises(VerifierExecutionError) as caught:
        verifier.verify(_task(verifier), Session.create("empty"))
    assert caught.value.phase == "verification"
    assert caught.value.task_id == "task"
