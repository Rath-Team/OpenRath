"""Built-in sandbox-facing tools and ``flow_tool_*`` session helpers.

``flow_tool_*`` functions build the matching :class:`~rath.backend.tool_types.BackendTool`
payload and run :meth:`~rath.session.session.Session.require_sandbox`'s
``dispatch``; they return the backend result object(s).

Each :class:`FlowToolCall` subclass mirrors one helper and is registered in
:func:`global_system_tools` for the session loop.
"""

from __future__ import annotations

import types as _types
from collections.abc import Mapping, Sequence
from threading import Lock
from typing import Any

from rath.backend.tool_types import (
    BackendToolCodeRun,
    BackendToolCommandRun,
    BackendToolFilesExists,
    BackendToolFilesList,
    BackendToolFilesRead,
    BackendToolFilesWrite,
)
from rath.flow.tool.base import FlowToolCall
from rath.session.session import Session

__all__ = [
    "FlowToolCodeRun",
    "FlowToolCommandRun",
    "FlowToolFilesExists",
    "FlowToolFilesList",
    "FlowToolFilesRead",
    "FlowToolFilesWrite",
    "flow_tool_code_run",
    "flow_tool_command_run",
    "flow_tool_files_exists",
    "flow_tool_files_list",
    "flow_tool_files_read",
    "flow_tool_files_write",
    "global_system_tools",
]


def flow_tool_command_run(
    session: Session,
    cmd: str | Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    cwd: str | None = None,
    stdin: bytes | None = None,
    timeout: float | None = None,
) -> Any:
    call = BackendToolCommandRun(
        cmd=cmd, env=env, cwd=cwd, stdin=stdin, timeout=timeout
    )
    return session.require_sandbox().dispatch(call)


def flow_tool_files_read(
    session: Session, path: str, *, encoding: str | None = "utf-8"
) -> Any:
    call = BackendToolFilesRead(path=path, encoding=encoding)
    return session.require_sandbox().dispatch(call)


def flow_tool_files_write(
    session: Session,
    path: str,
    data: bytes | str,
    *,
    mode: int = 0o644,
) -> Any:
    call = BackendToolFilesWrite(path=path, data=data, mode=mode)
    return session.require_sandbox().dispatch(call)


def flow_tool_files_list(session: Session, path: str) -> Any:
    call = BackendToolFilesList(path=path)
    return session.require_sandbox().dispatch(call)


def flow_tool_files_exists(session: Session, path: str) -> Any:
    call = BackendToolFilesExists(path=path)
    return session.require_sandbox().dispatch(call)


def flow_tool_code_run(
    session: Session,
    code: str,
    *,
    language: str = "python",
    timeout: float | None = None,
) -> Any:
    call = BackendToolCodeRun(code=code, language=language, timeout=timeout)
    return session.require_sandbox().dispatch(call)


# All filesystem tools share one resource-key namespace so that any mix of
# operations on the SAME path (write+read, write+stat, ...) lands in one serial
# lane and runs in transcript order. Distinct paths still fan out in parallel.
# Using a per-operation prefix here (``fs:write`` vs ``fs:read``) would let a
# write and a read of the same path run concurrently and race.
_FS_RESOURCE_NAMESPACE = "fs"


def _path_resource_key(arguments: Mapping[str, Any]) -> tuple[str, ...]:
    try:
        return (_FS_RESOURCE_NAMESPACE, str(arguments["path"]))
    except KeyError:
        return (_FS_RESOURCE_NAMESPACE, "<unknown>")


class FlowToolCommandRun(FlowToolCall):
    """Built-in LLM tool: run one shell command in the active sandbox."""

    parallel_safe = False

    def resource_key(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
        return ("exec",)

    @property
    def name(self) -> str:
        return "run_shell_command"

    @property
    def description(self) -> str | None:
        return (
            "Run one shell command inside the active sandbox workspace. "
            "Prefer short commands such as ``echo Hello``."
        )

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "type": "object",
            "properties": {
                "cmd": {
                    "type": "string",
                    "description": "Shell command string",
                },
            },
            "required": ["cmd"],
            "additionalProperties": False,
        }

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> Any:
        cmd = arguments["cmd"]
        if not isinstance(cmd, str):
            cmd = str(cmd)
        if "\n" in cmd or "\r" in cmd:
            raise ValueError("multiline commands are rejected")
        if len(cmd) > 2048:
            raise ValueError("command too long")
        return flow_tool_command_run(session, cmd)


class FlowToolFilesWrite(FlowToolCall):
    """Built-in LLM tool: write UTF-8 text into the sandbox workspace."""

    parallel_safe = True

    def resource_key(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
        return _path_resource_key(arguments)

    @property
    def name(self) -> str:
        return "write_workspace_file"

    @property
    def description(self) -> str | None:
        return "Write UTF-8 text to a path inside the sandbox workspace."

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        }

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> Any:
        path = str(arguments["path"])
        raw = arguments["content"]
        if not isinstance(raw, str):
            raise TypeError("content must be text for write_workspace_file")
        return flow_tool_files_write(session, path, raw)


class FlowToolFilesRead(FlowToolCall):
    """Built-in LLM tool: read a file from the sandbox workspace."""

    parallel_safe = True

    def resource_key(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
        return _path_resource_key(arguments)

    @property
    def name(self) -> str:
        return "read_workspace_file"

    @property
    def description(self) -> str | None:
        return (
            "Read a file from the sandbox workspace. "
            "Omit encoding or set null to return raw bytes."
        )

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "encoding": {
                    "type": ["string", "null"],
                    "description": "Text encoding; null for binary",
                    "default": "utf-8",
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> Any:
        path = str(arguments["path"])
        enc = arguments.get("encoding", "utf-8")
        if enc is not None and not isinstance(enc, str):
            enc = str(enc)
        return flow_tool_files_read(session, path, encoding=enc)


class FlowToolFilesList(FlowToolCall):
    """Built-in LLM tool: list directory entries under a sandbox path."""

    parallel_safe = True

    def resource_key(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
        return _path_resource_key(arguments)

    @property
    def name(self) -> str:
        return "list_workspace_files"

    @property
    def description(self) -> str | None:
        return "List non-recursive directory entries under a sandbox path."

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> Any:
        return flow_tool_files_list(session, str(arguments["path"]))


class FlowToolFilesExists(FlowToolCall):
    """Built-in LLM tool: check whether a sandbox path exists."""

    parallel_safe = True

    def resource_key(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
        return _path_resource_key(arguments)

    @property
    def name(self) -> str:
        return "workspace_path_exists"

    @property
    def description(self) -> str | None:
        return "Return whether a path exists inside the sandbox workspace."

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> Any:
        return flow_tool_files_exists(session, str(arguments["path"]))


class FlowToolCodeRun(FlowToolCall):
    """Built-in LLM tool: execute code in the sandbox interpreter."""

    parallel_safe = False

    def resource_key(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
        return ("code",)

    @property
    def name(self) -> str:
        return "run_code"

    @property
    def description(self) -> str | None:
        return (
            "Execute a code snippet inside the sandbox code interpreter "
            "(default language: python)."
        )

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "language": {
                    "type": "string",
                    "description": "Interpreter language",
                    "default": "python",
                },
                "timeout": {
                    "type": ["number", "null"],
                    "description": "Optional timeout in seconds",
                },
            },
            "required": ["code"],
            "additionalProperties": False,
        }

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> Any:
        code = str(arguments["code"])
        language = str(arguments.get("language", "python"))
        timeout_raw = arguments.get("timeout")
        timeout = float(timeout_raw) if timeout_raw is not None else None
        return flow_tool_code_run(session, code, language=language, timeout=timeout)


_BUILTIN_TOOL_CLASSES: tuple[type[FlowToolCall], ...] = (
    FlowToolCommandRun,
    FlowToolFilesRead,
    FlowToolFilesWrite,
    FlowToolFilesList,
    FlowToolFilesExists,
    FlowToolCodeRun,
)

_SYSTEM: dict[str, FlowToolCall] | None = None
_SYSTEM_LOCK = Lock()


def global_system_tools() -> Mapping[str, FlowToolCall]:
    """Process-wide built-in tools (singleton instances per name, immutable view).

    Returns a :class:`types.MappingProxyType` over the internal registry
    so callers cannot accidentally mutate the global state via the
    returned object. Callers that need a mutable working copy can still
    do ``dict(global_system_tools())``; that explicit copy is local and
    does not touch the underlying registry.
    """

    global _SYSTEM
    with _SYSTEM_LOCK:
        if _SYSTEM is None:
            instances = [cls() for cls in _BUILTIN_TOOL_CLASSES]
            _SYSTEM = {tool.name: tool for tool in instances}
        return _types.MappingProxyType(_SYSTEM)
