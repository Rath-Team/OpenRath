"""Built-in sandbox-facing tools and ``flow_tool_*`` session helpers.

``flow_tool_*`` functions build the matching :class:`~rath.backend.tool_types.BackendTool`
payload and run :meth:`~rath.session.session.Session.require_sandbox`'s
``dispatch``; they return the backend result object(s).
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
    "RunShellCommandTool",
    "WriteWorkspaceFileTool",
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


class RunShellCommandTool(FlowToolCall):
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
        call = BackendToolCommandRun(cmd=cmd)
        return session.require_sandbox().dispatch(call)


class WriteWorkspaceFileTool(FlowToolCall):
    parallel_safe = True

    def resource_key(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
        try:
            path = str(arguments["path"])
        except KeyError:
            return ("fs:write", "<unknown>")
        return ("fs:write", path)

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
        if isinstance(raw, str):
            call = BackendToolFilesWrite(path=path, data=raw)
            return session.require_sandbox().dispatch(call)
        raise TypeError("content must be text for write_workspace_file")


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
            shell = RunShellCommandTool()
            write = WriteWorkspaceFileTool()
            _SYSTEM = {shell.name: shell, write.name: write}
        return _types.MappingProxyType(_SYSTEM)
