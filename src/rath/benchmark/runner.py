"""Run-local benchmark state machine over :class:`rath.env.OpenRathEnv`."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from rath.benchmark.errors import VerifierExecutionError
from rath.benchmark.result import BenchmarkRunResult
from rath.benchmark.task import BenchmarkTask
from rath.benchmark.verifier import VerificationResult
from rath.env import (
    EnvObservation,
    OpenRathEnv,
    OpenRathEnvConfig,
    RewardResult,
    ToolAction,
    observation_from_session,
)
from rath.session import Session

__all__ = ["BenchmarkRunner", "PolicyFn"]

PolicyFn = Callable[
    [BenchmarkTask, EnvObservation], ToolAction | Mapping[str, Any] | None
]


@dataclass(slots=True)
class _RunVerificationState:
    latest: VerificationResult | None = None
    verified_step_index: int | None = None
    pending_step_index: int | None = None


def _error_payload(exc: BaseException, phase: str) -> dict[str, Any]:
    return {
        "phase": phase,
        "type": type(exc).__name__,
        "message": str(exc),
    }


def _cause_is(exc: BaseException, expected: type[BaseException]) -> bool:
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, expected):
            return True
        current = current.__cause__
    return False


class BenchmarkRunner:
    """Reusable, thread-safe benchmark runner with no cross-run state."""

    __slots__ = ("task", "env_config")

    def __init__(
        self,
        task: BenchmarkTask,
        *,
        env_config: OpenRathEnvConfig | None = None,
    ) -> None:
        self.task = task
        self.env_config = env_config or OpenRathEnvConfig(max_steps=task.max_steps)

    def effective_env_config(self) -> OpenRathEnvConfig:
        """Env config for this task: the task's own image wins over the default."""

        return replace(
            self.env_config,
            max_steps=(
                self.task.max_steps
                if self.task.max_steps is not None
                else self.env_config.max_steps
            ),
            sandbox_spec=(
                self.task.sandbox_spec
                if self.task.sandbox_spec is not None
                else self.env_config.sandbox_spec
            ),
        )

    def run(self, policy: PolicyFn, *, fail_fast: bool = True) -> BenchmarkRunResult:
        state = _RunVerificationState()

        def _reward(
            session: Session, _action: ToolAction, _raw_result: Any
        ) -> RewardResult:
            verification = self.task.verifier.verify(self.task, session)
            state.latest = verification
            state.verified_step_index = state.pending_step_index
            return verification.to_reward_result()

        config = replace(self.effective_env_config(), reward_fn=_reward)
        env = OpenRathEnv(config)
        observation: EnvObservation | None = None
        try:
            try:
                observation = env.reset(self.task.prompt())
            except Exception as exc:
                if fail_fast:
                    raise
                return self._result(
                    env,
                    observation,
                    state.latest,
                    status="setup_failed",
                    error=_error_payload(exc, "setup"),
                    verified_step_index=state.verified_step_index,
                )

            try:
                assert env.session is not None
                self.task.prepare(env.session)
            except Exception as exc:
                self._finalize_error(env, "setup_failed", exc, "setup")
                if fail_fast:
                    raise
                return self._result(
                    env,
                    self._current_observation(env, observation),
                    state.latest,
                    status="setup_failed",
                    error=_error_payload(exc, "setup"),
                    verified_step_index=state.verified_step_index,
                )

            while True:
                try:
                    action = policy(self.task, observation)
                except Exception as exc:
                    self._finalize_error(env, "policy_failed", exc, "policy")
                    if fail_fast:
                        raise
                    return self._result(
                        env,
                        self._current_observation(env, observation),
                        state.latest,
                        status="policy_failed",
                        error=_error_payload(exc, "policy"),
                        verified_step_index=state.verified_step_index,
                    )

                if action is None:
                    terminal_reward = 0.0
                    verification = state.latest
                    if (
                        verification is None
                        or state.verified_step_index != env.step_count - 1
                    ):
                        try:
                            assert env.session is not None
                            verification = self.task.verifier.verify(
                                self.task, env.session
                            )
                        except Exception as exc:
                            self._finalize_error(
                                env, "verification_failed", exc, "verification"
                            )
                            if fail_fast:
                                raise
                            return self._result(
                                env,
                                self._current_observation(env, observation),
                                None,
                                status="verification_failed",
                                error=_error_payload(exc, "verification"),
                                verified_step_index=state.verified_step_index,
                            )
                        state.latest = verification
                        state.verified_step_index = None
                        terminal_reward = verification.reward
                    observation = self._current_observation(env, observation)
                    if verification.passed:
                        env.finish(
                            status="completed",
                            terminal_reward=terminal_reward,
                            terminated=True,
                        )
                        status = "completed"
                    else:
                        env.finish(
                            status="stopped",
                            terminal_reward=terminal_reward,
                        )
                        status = "stopped"
                    return self._result(
                        env,
                        observation,
                        verification,
                        status=status,
                        error=None,
                        verified_step_index=state.verified_step_index,
                    )

                state.pending_step_index = env.step_count
                try:
                    step_result = env.step(action)
                except Exception as exc:
                    verification_failure = _cause_is(exc, VerifierExecutionError)
                    status = (
                        "verification_failed" if verification_failure else "tool_failed"
                    )
                    phase = "verification" if verification_failure else "tool"
                    if env.state == "running":
                        self._finalize_error(env, status, exc, phase)
                    if fail_fast:
                        raise
                    return self._result(
                        env,
                        self._current_observation(env, observation),
                        state.latest,
                        status=status,
                        error=_error_payload(exc, phase),
                        verified_step_index=state.verified_step_index,
                    )

                observation = step_result.observation
                verification = state.latest
                if step_result.done:
                    status = "completed" if step_result.terminated else "max_steps"
                    return self._result(
                        env,
                        observation,
                        verification,
                        status=status,
                        error=None,
                        verified_step_index=state.verified_step_index,
                    )
                if step_result.info.get("tool_failed"):
                    step = env.trajectory[-1]
                    error = dict(
                        step.error or {"phase": "tool", "message": "tool failed"}
                    )
                    env.finish(status="tool_failed", error=error)
                    return self._result(
                        env,
                        observation,
                        verification,
                        status="tool_failed",
                        error=error,
                        verified_step_index=state.verified_step_index,
                    )
        finally:
            env.close()

    def _finalize_error(
        self,
        env: OpenRathEnv,
        status: str,
        exc: BaseException,
        phase: str,
    ) -> None:
        if env.state != "running":
            return
        try:
            env.finish(
                status=status,
                error=_error_payload(exc, phase),
                abandon=True,
            )
        except Exception:
            # The primary phase error remains authoritative. OpenRathEnv still
            # attempts reverse-order cleanup inside finish().
            pass

    @staticmethod
    def _current_observation(
        env: OpenRathEnv, fallback: EnvObservation | None
    ) -> EnvObservation | None:
        if env.session is None:
            return fallback
        try:
            return observation_from_session(env.session)
        except Exception:
            return fallback

    def _result(
        self,
        env: OpenRathEnv,
        observation: EnvObservation | None,
        verification: VerificationResult | None,
        *,
        status: str,
        error: Mapping[str, Any] | None,
        verified_step_index: int | None = None,
    ) -> BenchmarkRunResult:
        passed = bool(
            status == "completed" and verification is not None and verification.passed
        )
        return BenchmarkRunResult(
            task=self.task,
            passed=passed,
            verification=verification,
            observation=observation,
            trajectory_episode=env.trajectory_episode,
            status=status,
            error=error,
            # None when the verification describes the final workspace rather than
            # the state left behind by one particular action.
            metadata={"verified_step_index": verified_step_index},
        )
