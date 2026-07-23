"""Shared flow-tool dispatch, coordination, and result projection."""

from __future__ import annotations

import json
import logging
import threading
import weakref
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from rath.backend import (
    CodeResult,
    CommandResult,
    FileContent,
    FileEntries,
    FileWriteResult,
    ToolExecutionFailure,
    ToolResult,
)
from rath.flow.tool.base import FlowToolCall
from rath.session.session import Session, _enter_tool_dispatch, _exit_tool_dispatch
from rath.utils.decoding import decode_subprocess_output

__all__ = [
    "ToolDispatchResult",
    "dispatch_flow_tool",
    "project_tool_result",
    "serialize_tool_result",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ToolDispatchResult:
    """Auditable outcome of one coordinated flow-tool invocation."""

    raw: Any
    content: str
    projection: Any
    failed: bool


class _ToolCoordinator:
    """Per-instance lanes: same lane → serial, different lane → concurrent."""

    __slots__ = ("_guard", "_lane_locks")

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._lane_locks: dict[tuple[str, ...], threading.Lock] = {}

    def lock_for(self, lane: tuple[str, ...]) -> threading.Lock:
        with self._guard:
            lock = self._lane_locks.get(lane)
            if lock is None:
                lock = threading.Lock()
                self._lane_locks[lane] = lock
            return lock


def _lane_for(
    session: Session, tool: FlowToolCall, resource_key: tuple[str, ...]
) -> tuple[str, ...]:
    """Name the lane this call serializes on within its tool instance.

    An unsafe tool collapses to one lane so the instance never runs twice at
    once; a parallel-safe tool gets one lane per ``resource_key``. A
    ``sandbox_scoped`` tool then narrows the lane to the calling session's
    sandbox: the built-ins are process-wide singletons, so without this every
    sandbox in the process would contend on one lane and independent
    environments could not run their tools in parallel.
    """

    lane = ("unsafe",) if not tool.parallel_safe else ("safe", *resource_key)
    if not tool.sandbox_scoped:
        return lane
    sandbox = session.sandbox
    handle = None if sandbox is None else getattr(sandbox, "handle", None)
    # Sessions may share one sandbox (the loop shares the user session's), so
    # key on the sandbox itself; fall back to the session while it is unopened.
    scope = f"sandbox:{handle}" if handle is not None else f"session:{session.id}"
    return (*lane, scope)


_COORDINATORS_GUARD = threading.Lock()
_COORDINATORS: dict[
    int, tuple[weakref.ReferenceType[FlowToolCall], _ToolCoordinator]
] = {}


def _coordinator_for(tool: FlowToolCall) -> _ToolCoordinator:
    ident = id(tool)
    with _COORDINATORS_GUARD:
        existing = _COORDINATORS.get(ident)
        if existing is not None and existing[0]() is tool:
            return existing[1]

        coordinator = _ToolCoordinator()

        def _discard(ref: weakref.ReferenceType[FlowToolCall]) -> None:
            with _COORDINATORS_GUARD:
                current = _COORDINATORS.get(ident)
                if current is not None and current[0] is ref:
                    _COORDINATORS.pop(ident, None)

        ref = weakref.ref(tool, _discard)
        _COORDINATORS[ident] = (ref, coordinator)
        return coordinator


def _execution_failure(exc: BaseException) -> ToolExecutionFailure:
    return ToolExecutionFailure(
        kind="tool_execution_exception",
        message=f"{type(exc).__name__}: {exc}",
        detail=type(exc).__name__,
    )


def dispatch_flow_tool(
    session: Session,
    tool: FlowToolCall,
    arguments: Mapping[str, Any],
) -> ToolDispatchResult:
    """Invoke one tool under its instance/resource concurrency contract.

    Both ``resource_key()`` and tool-body exceptions are converted into a
    :class:`ToolExecutionFailure`, so every started dispatch has a serializable
    result suitable for a Session chunk or compact trajectory.
    """

    args = dict(arguments or {})

    # The policy gate sits before the tool body, not inside it: a denied call must
    # not run. The denial is an auditable result, not an exception, so the model
    # sees a refusal it can react to and the episode survives it.
    enforcer = session._policy_enforcer
    if enforcer is not None:
        denial = enforcer.check(tool.name, args)
        if denial is not None:
            denied = ToolExecutionFailure(
                kind="tool_policy_denied",
                message=denial,
                detail=tool.name,
            )
            return ToolDispatchResult(
                raw=denied,
                content=serialize_tool_result(tool, denied),
                projection=project_tool_result(tool, denied),
                failed=True,
            )

    _enter_tool_dispatch()
    try:
        try:
            raw_key = tool.resource_key(args)
            resource_key = tuple(str(part) for part in raw_key)
        except Exception as exc:  # noqa: BLE001 - tool boundary
            logger.exception("resource_key failed for tool=%s", tool.name)
            raw: Any = _execution_failure(exc)
        else:
            lane = _lane_for(session, tool, resource_key)
            with _coordinator_for(tool).lock_for(lane):
                try:
                    raw = tool(session, args)
                except Exception as exc:  # noqa: BLE001 - tool boundary
                    # The failure becomes an auditable ToolExecutionFailure, so
                    # this is the only place the traceback still exists.
                    logger.exception("tool invocation failed for tool=%s", tool.name)
                    raw = _execution_failure(exc)
    finally:
        _exit_tool_dispatch()

    projection = project_tool_result(tool, raw)
    return ToolDispatchResult(
        raw=raw,
        content=serialize_tool_result(tool, raw),
        projection=projection,
        failed=isinstance(raw, ToolExecutionFailure),
    )


def _project_inline_result(raw: Any) -> Any:
    if isinstance(raw, BaseModel):
        payload: Any = raw.model_dump(mode="json")
    else:
        payload = raw
    try:
        # ``default=str`` keeps datetimes, Paths, and friends readable instead of
        # collapsing the whole result into the repr fallback below.
        text = json.dumps(payload, ensure_ascii=False, default=str)
        if len(text) > 48_000:
            return {
                "repr": repr(payload)[:47_000] + "...(truncated)",
                "type": type(payload).__name__,
            }
        # Round-tripping makes the projection exactly match the emitted JSON
        # body while preserving historical scalar/list return shapes.
        normalized = json.loads(text)
        return normalized
    except (TypeError, ValueError):
        return {"repr": repr(raw), "type": type(raw).__name__}


def project_tool_result(tool: FlowToolCall, raw: Any) -> Any:
    """Project a raw flow-tool return value into its transcript payload."""

    del tool
    if isinstance(raw, ToolExecutionFailure):
        return {
            "ok": False,
            "error_kind": raw.kind,
            "message": raw.message,
            **({"detail": raw.detail} if raw.detail else {}),
        }
    if isinstance(raw, bool):
        return {"ok": raw}
    if isinstance(raw, CommandResult):
        return {
            "exit_code": raw.exit_code,
            "stdout": decode_subprocess_output(raw.stdout),
            "stderr": decode_subprocess_output(raw.stderr),
            "elapsed_ms": raw.elapsed_ms,
        }
    if isinstance(raw, FileContent):
        data = raw.data
        if isinstance(data, bytes):
            data = decode_subprocess_output(data)
        text = str(data)
        if len(text) > 12_000:
            text = text[:12_000] + "...(truncated)"
        return {"data": text}
    if isinstance(raw, FileEntries):
        return {
            "entries": [
                {"name": entry.name, "path": entry.path, "is_dir": entry.is_dir}
                for entry in raw.entries[:500]
            ]
        }
    if isinstance(raw, FileWriteResult):
        return {"bytes_written": raw.bytes_written}
    if isinstance(raw, CodeResult):
        return {
            "text": raw.text,
            "stdout": decode_subprocess_output(raw.stdout),
            "stderr": decode_subprocess_output(raw.stderr),
            "error": raw.error,
        }
    if isinstance(raw, ToolResult):
        return {"type": type(raw).__name__, "note": "unserialised result"}
    return _project_inline_result(raw)


def serialize_tool_result(tool: FlowToolCall, raw: Any) -> str:
    """Serialize a tool result using the session loop's established encoding."""

    projection = project_tool_result(tool, raw)
    # Sandbox results have always been ASCII-escaped and inline tool returns have
    # always been emitted raw; keep both byte-for-byte rather than unifying here.
    return json.dumps(projection, ensure_ascii=isinstance(raw, (ToolResult, bool)))
