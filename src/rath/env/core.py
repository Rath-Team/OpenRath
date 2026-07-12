"""Transactional environment-style execution over OpenRath tools."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from rath.backend import BackendSandboxSpec
from rath.env.actions import ToolAction
from rath.env.errors import (
    EnvSetupError,
    EnvStepError,
    TrajectoryPersistenceError,
)
from rath.env.observations import (
    EnvObservation,
    chunk_to_jsonable,
    jsonable_value,
    observation_from_session,
)
from rath.env.rewards import RewardFn, RewardResult
from rath.env.trajectory import (
    TrajectoryEpisode,
    TrajectoryEpisodeEnd,
    TrajectoryEpisodeStart,
    TrajectoryStep,
    trajectory_to_jsonl,
    write_trajectory_jsonl,
)
from rath.flow.tool import (
    FlowToolCall,
    ToolPolicy,
    dispatch_flow_tool,
    merge_tools_for_loop,
)
from rath.llm import RathLLMToolCallFunction, RathLLMToolCallPart
from rath.persistence import JsonlAppendWriter
from rath.session import (
    Session,
    SessionWriter,
    assistant_turn_chunk,
    tool_feedback_chunk,
)

__all__ = ["OpenRathEnv", "OpenRathEnvConfig", "StepResult"]


class _EnvState(str, Enum):
    NEW = "new"
    RUNNING = "running"
    DONE = "done"
    FAULTED = "faulted"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class StepResult:
    observation: EnvObservation
    reward: float
    terminated: bool
    truncated: bool
    info: dict[str, Any]

    def __post_init__(self) -> None:
        validated = RewardResult(self.reward, self.terminated, self.info)
        object.__setattr__(self, "reward", validated.reward)
        object.__setattr__(self, "info", dict(validated.info))
        object.__setattr__(self, "terminated", bool(self.terminated))
        object.__setattr__(self, "truncated", bool(self.truncated))
        if self.terminated and self.truncated:
            raise ValueError("StepResult cannot be terminated and truncated")

    @property
    def done(self) -> bool:
        return self.terminated or self.truncated


ToolFactory = Callable[[], Sequence[FlowToolCall]]


@dataclass(frozen=True, slots=True)
class OpenRathEnvConfig:
    """Configuration for a dependency-light OpenRath execution environment."""

    backend: str = "opensandbox"
    sandbox_spec: BackendSandboxSpec | str | None = None
    tools: Sequence[FlowToolCall] | None = None
    tools_factory: ToolFactory | None = None
    reward_fn: RewardFn | None = None
    max_steps: int | None = None
    tool_policy: ToolPolicy | None = None
    persist_trajectory: bool = False
    trajectory_path: str | Path | None = None
    episode_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.backend, str) or not self.backend.strip():
            raise ValueError("backend must be a non-empty string")
        if self.max_steps is not None:
            if type(self.max_steps) is not int or self.max_steps <= 0:
                raise ValueError("max_steps must be a positive integer when set")
        if self.tools is not None and self.tools_factory is not None:
            raise ValueError("pass tools or tools_factory, not both")
        if self.tools is not None:
            object.__setattr__(self, "tools", tuple(self.tools))
        metadata = jsonable_value(dict(self.episode_metadata), path="episode_metadata")
        assert isinstance(metadata, dict)
        object.__setattr__(self, "episode_metadata", MappingProxyType(metadata))
        if self.trajectory_path is not None:
            object.__setattr__(self, "trajectory_path", Path(self.trajectory_path))


def _error_payload(exc: BaseException, phase: str) -> dict[str, Any]:
    return {
        "phase": phase,
        "type": type(exc).__name__,
        "message": str(exc),
    }


class OpenRathEnv:
    """Environment-style transactional tool executor; it is not a Gym API."""

    __slots__ = (
        "config",
        "_state",
        "_session",
        "_tools",
        "_writer",
        "_step_count",
        "_trajectory_start",
        "_trajectory_steps",
        "_trajectory_end",
        "_trajectory_writer",
    )

    def __init__(self, config: OpenRathEnvConfig | None = None) -> None:
        self.config = config or OpenRathEnvConfig()
        self._state = _EnvState.NEW
        self._session: Session | None = None
        self._tools: dict[str, FlowToolCall] = {}
        self._writer: SessionWriter | None = None
        self._step_count = 0
        self._trajectory_start: TrajectoryEpisodeStart | None = None
        self._trajectory_steps: list[TrajectoryStep] = []
        self._trajectory_end: TrajectoryEpisodeEnd | None = None
        self._trajectory_writer: JsonlAppendWriter | None = None

    @property
    def state(self) -> str:
        return self._state.value

    @property
    def session(self) -> Session | None:
        return self._session

    @property
    def step_count(self) -> int:
        return self._step_count

    @property
    def trajectory(self) -> tuple[TrajectoryStep, ...]:
        return tuple(self._trajectory_steps)

    @property
    def trajectory_episode(self) -> TrajectoryEpisode | None:
        if self._trajectory_start is None:
            return None
        return TrajectoryEpisode(
            self._trajectory_start,
            tuple(self._trajectory_steps),
            self._trajectory_end,
        )

    def reset(self, task: str | Session | None = None) -> EnvObservation:
        """Transactionally acquire a fresh Session, sandbox, and episode sinks."""

        if self._state is _EnvState.CLOSED:
            raise RuntimeError("OpenRathEnv is closed")
        if self._state is _EnvState.RUNNING:
            cleanup_errors = self._abandon_current("reset")
            if cleanup_errors:
                primary = cleanup_errors[0]
                raise EnvSetupError(
                    "failed to abandon the previous episode before reset",
                    phase="previous_episode_cleanup",
                    cleanup_errors=cleanup_errors[1:],
                ) from primary
        else:
            self._release_resources(close_writer=False)

        session: Session | None = None
        writer: SessionWriter | None = None
        trajectory_writer: JsonlAppendWriter | None = None
        phase = "tools"
        try:
            tools = self._build_tools()
            phase = "session"
            session = self._build_initial_session(task)
            session.tool_policy = self.config.tool_policy
            phase = "sandbox"
            session.to(self.config.backend, spec=self.config.sandbox_spec)
            sandbox = session.require_sandbox()
            if self.config.persist_trajectory:
                phase = "session_writer"
                writer = SessionWriter(session, sandbox_handle_id=sandbox.handle)
                phase = "session_writer_seed"
                for index, row in enumerate(session.chunk_table.rows):
                    writer.write_chunk(index, row)
            phase = "initial_observation"
            observation = observation_from_session(session)
            start = TrajectoryEpisodeStart(
                episode_id=str(session.id),
                initial_observation=observation,
                metadata=self.config.episode_metadata,
            )
            if self.config.trajectory_path is not None:
                phase = "trajectory_writer"
                trajectory_writer = JsonlAppendWriter(self.config.trajectory_path)
            phase = "trajectory_start"
            self._persist_record(start, phase="episode_start", writer=trajectory_writer)
        except Exception as exc:
            cleanup_errors = self._cleanup_locals(
                session, writer, trajectory_writer, abandon=True
            )
            self._state = _EnvState.NEW
            self._session = None
            self._writer = None
            raise EnvSetupError(
                f"failed to reset OpenRathEnv during setup: {exc}",
                phase=phase,
                context={"backend": self.config.backend},
                cleanup_errors=cleanup_errors,
            ) from exc

        self._session = session
        self._tools = tools
        self._writer = writer
        self._step_count = 0
        self._trajectory_start = start
        self._trajectory_steps = []
        self._trajectory_end = None
        self._trajectory_writer = trajectory_writer
        self._state = _EnvState.RUNNING
        return observation

    def step(self, action: ToolAction | Mapping[str, Any]) -> StepResult:
        if self._state is _EnvState.CLOSED:
            raise RuntimeError("OpenRathEnv is closed")
        if self._state is _EnvState.NEW:
            raise RuntimeError("OpenRathEnv.reset() must be called before step()")
        if self._state is _EnvState.DONE:
            raise RuntimeError("OpenRathEnv episode is done; call reset()")
        if self._state is _EnvState.FAULTED:
            raise RuntimeError("OpenRathEnv episode is faulted; call reset()")
        assert self._session is not None

        act = (
            action
            if isinstance(action, ToolAction)
            else ToolAction.from_mapping(action)
        )
        tool = self._tools.get(act.tool_name)
        if tool is None:
            available = ", ".join(sorted(self._tools))
            raise ValueError(
                f"unknown tool {act.tool_name!r}; available tools: {available}"
            )

        step_index = self._step_count
        self._step_count += 1
        chunk_start = len(self._session.chunk_table.rows)
        dispatch_result = None
        phase = "assistant_chunk"
        try:
            call_id = f"env_{self._session.id}_step_{step_index}"
            self._append_chunk(_assistant_tool_chunk(call_id, act))
            phase = "tool_dispatch"
            dispatch_result = dispatch_flow_tool(
                self._session, tool, dict(act.arguments)
            )
            trajectory_tool_result = _trajectory_tool_result(dispatch_result.projection)
            phase = "tool_result_chunk"
            self._append_chunk(
                tool_feedback_chunk(call_id, act.tool_name, dispatch_result.content)
            )
            phase = "reward"
            reward_result = self._compute_reward(act, dispatch_result.raw)
            info = dict(reward_result.info)
            if dispatch_result.failed:
                info.setdefault("tool_failed", True)
            terminated = reward_result.done
            truncated = False
            if (
                not terminated
                and self.config.max_steps is not None
                and self._step_count >= self.config.max_steps
            ):
                truncated = True
                info.setdefault("max_steps_reached", True)
            observation = observation_from_session(self._session)
            delta = self._transcript_delta(chunk_start)
            raw_error = trajectory_tool_result if dispatch_result.failed else None
            step = TrajectoryStep(
                episode_id=str(self._session.id),
                step_index=step_index,
                action=act,
                transcript_delta=delta,
                tool_result=trajectory_tool_result,
                reward=reward_result.reward,
                terminated=terminated,
                truncated=truncated,
                info=info,
                status="tool_failed" if dispatch_result.failed else "completed",
                error=raw_error,
            )
        except Exception as exc:
            self._raise_started_action_failure(
                exc,
                phase=phase,
                action=act,
                step_index=step_index,
                chunk_start=chunk_start,
                tool_result=(
                    None
                    if dispatch_result is None
                    else _trajectory_tool_result(dispatch_result.projection)
                ),
            )
            raise AssertionError("unreachable")

        self._trajectory_steps.append(step)
        try:
            self._persist_record(step, phase="step")
        except Exception as exc:
            failed_step = replace(
                step,
                status="failed",
                error=_error_payload(exc, "trajectory_step_persistence"),
            )
            self._trajectory_steps[-1] = failed_step
            self._fault_after_existing_step(
                exc, failed_step, phase="trajectory_step_persistence"
            )
            raise AssertionError("unreachable")

        if step.done:
            status = "completed" if step.terminated else "max_steps"
            try:
                self._finalize_episode(
                    status=status,
                    terminal_reward=0.0,
                    terminated=step.terminated,
                    truncated=step.truncated,
                    final_observation=observation,
                    abandon_writer=False,
                )
            except Exception as exc:
                self._fault_after_existing_step(exc, step, phase="finalize")
                raise AssertionError("unreachable")

        return StepResult(
            observation=observation,
            reward=step.reward,
            terminated=step.terminated,
            truncated=step.truncated,
            info=dict(step.info),
        )

    def finish(
        self,
        *,
        status: str = "stopped",
        terminal_reward: float = 0.0,
        terminated: bool = False,
        truncated: bool = False,
        metadata: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
        abandon: bool = False,
    ) -> TrajectoryEpisodeEnd:
        """Finalize an episode after policy stop or terminal verification."""

        if self._state is not _EnvState.RUNNING:
            raise RuntimeError("finish() requires a running episode")
        assert self._session is not None
        final_observation = observation_from_session(self._session)
        return self._finalize_episode(
            status=status,
            terminal_reward=terminal_reward,
            terminated=terminated,
            truncated=truncated,
            final_observation=final_observation,
            metadata=metadata,
            error=error,
            abandon_writer=abandon,
        )

    def trajectory_jsonl(self) -> str:
        episode = self.trajectory_episode
        return "" if episode is None else trajectory_to_jsonl(episode)

    def export_trajectory_jsonl(
        self, path: str | Path, *, append: bool = False
    ) -> None:
        episode = self.trajectory_episode
        if episode is None:
            write_trajectory_jsonl((), path, append=append)
            return
        try:
            write_trajectory_jsonl(episode, path, append=append)
        except Exception as exc:
            raise TrajectoryPersistenceError(
                f"failed to export trajectory to {path}: {exc}",
                phase="export",
                context={"path": str(path)},
            ) from exc

    def close(self) -> None:
        if self._state is _EnvState.CLOSED:
            return
        primary: BaseException | None = None
        cleanup_errors: list[BaseException] = []
        if self._state is _EnvState.RUNNING:
            cleanup_errors.extend(self._abandon_current("close"))
            if cleanup_errors:
                primary = cleanup_errors.pop(0)
        else:
            cleanup_errors.extend(self._release_resources(close_writer=False))
        self._state = _EnvState.CLOSED
        if primary is not None:
            raise TrajectoryPersistenceError(
                f"failed while closing OpenRathEnv: {primary}",
                phase="close",
                cleanup_errors=cleanup_errors,
            ) from primary

    def __enter__(self) -> "OpenRathEnv":
        if self._state is _EnvState.CLOSED:
            raise RuntimeError("OpenRathEnv is closed")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        if exc is not None and self._state is _EnvState.RUNNING:
            self._abandon_current("context_exception", error=exc)
            self._state = _EnvState.CLOSED
            return
        self.close()

    def _build_tools(self) -> dict[str, FlowToolCall]:
        tools = (
            tuple(self.config.tools_factory())
            if self.config.tools_factory is not None
            else self.config.tools
        )
        return merge_tools_for_loop(None if tools is None else list(tools))

    @staticmethod
    def _build_initial_session(task: str | Session | None) -> Session:
        if task is None:
            return Session.create("empty")
        if isinstance(task, Session):
            session = task.fork()
            session.close_sandbox()
            return session
        return Session.create("user", str(task))

    def _append_chunk(self, row: Any) -> None:
        assert self._session is not None
        index = self._session.append_chunk(row)
        if self._writer is not None:
            self._writer.write_chunk(index, row)

    def _compute_reward(self, action: ToolAction, raw_result: Any) -> RewardResult:
        if self.config.reward_fn is None:
            return RewardResult()
        assert self._session is not None
        result = self.config.reward_fn(self._session, action, raw_result)
        if not isinstance(result, RewardResult):
            raise TypeError("reward_fn must return RewardResult")
        return result

    def _transcript_delta(self, start: int) -> tuple[dict[str, Any], ...]:
        assert self._session is not None
        return tuple(
            chunk_to_jsonable(row) for row in self._session.chunk_table.rows[start:]
        )

    def _persist_record(
        self,
        record: Any,
        *,
        phase: str,
        writer: JsonlAppendWriter | None = None,
    ) -> None:
        path = self.config.trajectory_path
        if path is None:
            return
        try:
            active_writer = self._trajectory_writer if writer is None else writer
            if active_writer is None:
                raise RuntimeError("trajectory append writer is not available")
            active_writer.append((record.to_jsonable(),))
        except Exception as exc:
            raise TrajectoryPersistenceError(
                f"failed to persist trajectory {phase} to {path}: {exc}",
                phase=phase,
                context={"path": str(path)},
            ) from exc

    def _make_end(
        self,
        *,
        status: str,
        terminal_reward: float,
        terminated: bool,
        truncated: bool,
        final_observation: EnvObservation | None,
        metadata: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
    ) -> TrajectoryEpisodeEnd:
        assert self._trajectory_start is not None
        transition_reward = float(sum(step.reward for step in self._trajectory_steps))
        return TrajectoryEpisodeEnd(
            episode_id=self._trajectory_start.episode_id,
            step_count=self._step_count,
            transition_reward=transition_reward,
            terminal_reward=terminal_reward,
            total_reward=transition_reward + float(terminal_reward),
            terminated=terminated,
            truncated=truncated,
            status=status,
            final_observation=final_observation,
            metadata={} if metadata is None else metadata,
            error=error,
        )

    def _finalize_episode(
        self,
        *,
        status: str,
        terminal_reward: float,
        terminated: bool,
        truncated: bool,
        final_observation: EnvObservation | None,
        metadata: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
        abandon_writer: bool,
    ) -> TrajectoryEpisodeEnd:
        end = self._make_end(
            status=status,
            terminal_reward=terminal_reward,
            terminated=terminated,
            truncated=truncated,
            final_observation=final_observation,
            metadata=metadata,
            error=error,
        )
        self._trajectory_end = end
        self._persist_record(end, phase="episode_end")
        cleanup_errors = self._release_resources(
            close_writer=not abandon_writer,
            abandon_writer=abandon_writer,
        )
        self._state = _EnvState.FAULTED if abandon_writer else _EnvState.DONE
        if cleanup_errors:
            raise cleanup_errors[0]
        return end

    def _raise_started_action_failure(
        self,
        exc: BaseException,
        *,
        phase: str,
        action: ToolAction,
        step_index: int,
        chunk_start: int,
        tool_result: Mapping[str, Any] | None,
    ) -> None:
        assert self._session is not None
        error = _error_payload(exc, phase)
        try:
            observation = observation_from_session(self._session)
        except Exception:
            observation = None
        step = TrajectoryStep(
            episode_id=str(self._session.id),
            step_index=step_index,
            action=action,
            transcript_delta=self._transcript_delta(chunk_start),
            tool_result=tool_result,
            reward=0.0,
            terminated=False,
            truncated=False,
            info={},
            status="failed",
            error=error,
        )
        self._trajectory_steps.append(step)
        cleanup_errors: list[BaseException] = []
        step_persisted = True
        try:
            self._persist_record(step, phase="failed_step")
        except Exception as persist_exc:
            step_persisted = False
            cleanup_errors.append(persist_exc)
        end = self._make_end(
            status="failed",
            terminal_reward=0.0,
            terminated=step.terminated,
            truncated=step.truncated,
            final_observation=observation,
            error=error,
        )
        self._trajectory_end = end
        if step_persisted:
            try:
                self._persist_record(end, phase="failed_episode_end")
            except Exception as persist_exc:
                cleanup_errors.append(persist_exc)
        cleanup_errors.extend(
            self._release_resources(close_writer=False, abandon_writer=True)
        )
        self._state = _EnvState.FAULTED
        raise EnvStepError(
            f"environment step failed during {phase}: {exc}",
            phase=phase,
            context={"episode_id": str(self._session.id), "step_index": step_index},
            cleanup_errors=cleanup_errors,
            step=step,
        ) from exc

    def _fault_after_existing_step(
        self, exc: BaseException, step: TrajectoryStep, *, phase: str
    ) -> None:
        assert self._session is not None
        error = _error_payload(exc, phase)
        try:
            observation = observation_from_session(self._session)
        except Exception:
            observation = None
        if self._trajectory_end is None:
            self._trajectory_end = self._make_end(
                status="failed",
                terminal_reward=0.0,
                terminated=step.terminated,
                truncated=step.truncated,
                final_observation=observation,
                error=error,
            )
        cleanup_errors = self._release_resources(
            close_writer=False, abandon_writer=True
        )
        self._state = _EnvState.FAULTED
        raise EnvStepError(
            f"environment step failed during {phase}: {exc}",
            phase=phase,
            context={
                "episode_id": str(self._session.id),
                "step_index": step.step_index,
            },
            cleanup_errors=cleanup_errors,
            step=step,
        ) from exc

    def _abandon_current(
        self, reason: str, *, error: BaseException | None = None
    ) -> list[BaseException]:
        cleanup_errors: list[BaseException] = []
        if self._trajectory_start is not None and self._trajectory_end is None:
            payload = None if error is None else _error_payload(error, reason)
            try:
                observation = (
                    None
                    if self._session is None
                    else observation_from_session(self._session)
                )
                end = self._make_end(
                    status="abandoned",
                    terminal_reward=0.0,
                    terminated=False,
                    truncated=False,
                    final_observation=observation,
                    metadata={"reason": reason},
                    error=payload,
                )
                self._trajectory_end = end
                self._persist_record(end, phase="abandon")
            except Exception as exc:
                cleanup_errors.append(exc)
        cleanup_errors.extend(
            self._release_resources(close_writer=False, abandon_writer=True)
        )
        self._state = _EnvState.NEW
        return cleanup_errors

    def _cleanup_locals(
        self,
        session: Session | None,
        writer: SessionWriter | None,
        trajectory_writer: JsonlAppendWriter | None,
        *,
        abandon: bool,
    ) -> list[BaseException]:
        errors: list[BaseException] = []
        if trajectory_writer is not None:
            try:
                trajectory_writer.close()
            except Exception as exc:
                errors.append(exc)
        if writer is not None:
            try:
                writer.abandon() if abandon else writer.close()
            except Exception as exc:
                errors.append(exc)
        if session is not None:
            try:
                session.close_sandbox()
            except Exception as exc:
                errors.append(exc)
        return errors

    def _release_resources(
        self,
        *,
        close_writer: bool,
        abandon_writer: bool = False,
    ) -> list[BaseException]:
        writer = self._writer
        self._writer = None
        trajectory_writer = self._trajectory_writer
        self._trajectory_writer = None
        session = self._session
        errors: list[BaseException] = []
        if trajectory_writer is not None:
            try:
                trajectory_writer.close()
            except Exception as exc:
                errors.append(exc)
        if writer is not None:
            try:
                if close_writer:
                    writer.close()
                elif abandon_writer:
                    writer.abandon()
            except Exception as exc:
                errors.append(exc)
        if session is not None:
            try:
                session.close_sandbox()
            except Exception as exc:
                errors.append(exc)
        return errors


def _assistant_tool_chunk(call_id: str, action: ToolAction) -> Any:
    arguments = jsonable_value(action.arguments, path="action.arguments")
    assert isinstance(arguments, dict)
    part = RathLLMToolCallPart(
        id=call_id,
        type="function",
        function=RathLLMToolCallFunction(
            name=action.tool_name,
            arguments=json.dumps(arguments, ensure_ascii=False, allow_nan=False),
            arguments_parsed=arguments,
            arguments_parse_error=False,
        ),
    )
    return assistant_turn_chunk(tool_calls=(part,), content=None)


def _trajectory_tool_result(projection: Any) -> Mapping[str, Any]:
    """Keep transcript compatibility while trajectories use an object shape."""

    if isinstance(projection, Mapping):
        return dict(projection)
    return {"value": jsonable_value(projection, path="tool_result")}
