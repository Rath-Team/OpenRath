"""Benchmark verifier protocol and sandbox command implementations."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol

from rath.backend import CommandResult, ToolExecutionFailure
from rath.benchmark.errors import VerifierExecutionError
from rath.benchmark.task import BenchmarkTask
from rath.env import RewardResult
from rath.env.observations import jsonable_value
from rath.flow.tool import flow_tool_command_run
from rath.session import Session
from rath.utils.decoding import decode_subprocess_output

__all__ = [
    "CommandVerifier",
    "PytestVerifier",
    "VerificationResult",
    "Verifier",
]


@dataclass(frozen=True, slots=True)
class VerificationResult:
    passed: bool
    reward: float
    score: float | None = None
    message: str = ""
    info: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        reward = float(self.reward)
        if not math.isfinite(reward):
            raise ValueError("verification reward must be finite")
        score = None if self.score is None else float(self.score)
        if score is not None and not math.isfinite(score):
            raise ValueError("verification score must be finite")
        if not isinstance(self.info, Mapping):
            raise TypeError("verification info must be a mapping")
        info = jsonable_value(deepcopy(dict(self.info)), path="verification.info")
        assert isinstance(info, dict)
        object.__setattr__(self, "passed", bool(self.passed))
        object.__setattr__(self, "reward", reward)
        object.__setattr__(self, "score", score)
        object.__setattr__(self, "info", MappingProxyType(info))

    def to_reward_result(self) -> RewardResult:
        info = dict(self.info)
        info.update(
            {
                "verification_passed": self.passed,
                "verification_score": self.score,
                "verification_message": self.message,
            }
        )
        return RewardResult(self.reward, self.passed, info)

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reward": self.reward,
            "score": self.score,
            "message": self.message,
            "info": jsonable_value(self.info, path="verification.info"),
        }


class Verifier(Protocol):
    def verify(self, task: BenchmarkTask, session: Session) -> VerificationResult: ...


@dataclass(frozen=True, slots=True)
class CommandVerifier:
    cmd: str | Sequence[str]
    timeout: float | None = 30.0
    cwd: str | None = None
    reward_pass: float = 1.0
    reward_fail: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.cmd, str):
            if not self.cmd.strip():
                raise ValueError("verifier cmd cannot be blank")
        else:
            command = [str(part) for part in self.cmd]
            if not command:
                raise ValueError("verifier cmd cannot be empty")
            object.__setattr__(self, "cmd", command)

    def verify(self, task: BenchmarkTask, session: Session) -> VerificationResult:
        raw = flow_tool_command_run(
            session,
            self.cmd,
            cwd=self.cwd,
            timeout=self.timeout,
        )
        if isinstance(raw, ToolExecutionFailure):
            raise VerifierExecutionError(
                f"verifier command could not execute: {raw.message}",
                task_id=task.task_id,
                phase="verification",
                context={
                    "error_kind": raw.kind,
                    "detail": raw.detail,
                    "cmd": self.cmd,
                },
            )
        if not isinstance(raw, CommandResult):
            raise VerifierExecutionError(
                f"unexpected verifier result {type(raw).__name__}",
                task_id=task.task_id,
                phase="verification",
                context={"result_type": type(raw).__name__, "cmd": self.cmd},
            )
        passed = raw.exit_code == 0
        return VerificationResult(
            passed=passed,
            reward=self.reward_pass if passed else self.reward_fail,
            score=1.0 if passed else 0.0,
            message="passed" if passed else "command failed",
            info={
                "task_id": task.task_id,
                "exit_code": raw.exit_code,
                "stdout": decode_subprocess_output(raw.stdout),
                "stderr": decode_subprocess_output(raw.stderr),
                "elapsed_ms": raw.elapsed_ms,
                "cmd": self.cmd,
            },
        )


@dataclass(frozen=True, slots=True)
class PytestVerifier(CommandVerifier):
    def __init__(
        self,
        args: Sequence[str] = ("-q",),
        *,
        python_command: str = "python",
        timeout: float | None = 30.0,
        cwd: str | None = None,
        reward_pass: float = 1.0,
        reward_fail: float = 0.0,
    ) -> None:
        CommandVerifier.__init__(
            self,
            cmd=[python_command, "-m", "pytest", *args],
            timeout=timeout,
            cwd=cwd,
            reward_pass=reward_pass,
            reward_fail=reward_fail,
        )
