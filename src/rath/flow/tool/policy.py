"""Capability bounds enforced where tools actually execute.

A model under training does whatever the environment permits. A permission that
lives in a prompt, or in an agent's default configuration, is a permission the
model can walk around. The only enforceable place is the single point every tool
call passes through: :func:`rath.flow.tool.dispatch.dispatch_flow_tool`.

Network isolation is deliberately *not* here. Denying ``curl`` by name cannot stop
``socket.connect`` inside an interpreter, and a bound that can be stepped over is
worse than no bound, because it reads like protection. The sandbox has to enforce
it; see :class:`rath.backend.BackendCapability.NETWORK_ISOLATION`.
"""

from __future__ import annotations

import shlex
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

__all__ = ["ToolPolicy", "ToolPolicyEnforcer"]


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    """What a session may reach. An empty or ``None`` field means "unrestricted"."""

    allow_tools: frozenset[str] | None = None
    fs_roots: tuple[str, ...] = ()
    command_allow: tuple[str, ...] = ()
    command_deny: tuple[str, ...] = ()
    max_calls: int | None = None

    def __post_init__(self) -> None:
        if self.max_calls is not None and self.max_calls < 0:
            raise ValueError("max_calls must be non-negative when set")
        if self.command_allow and self.command_deny:
            raise ValueError("pass command_allow or command_deny, not both")


def _normalize(parts: tuple[str, ...]) -> list[str]:
    """Resolve ``.`` and ``..`` textually; the path need not exist to be judged."""

    out: list[str] = []
    for part in parts:
        if part == "..":
            if out and out[-1] not in ("/", ""):
                out.pop()
            continue
        if part == ".":
            continue
        out.append(part)
    return out


def _first_token(value: Any) -> str | None:
    if isinstance(value, str):
        parts = shlex.split(value)
        return parts[0] if parts else None
    if isinstance(value, (list, tuple)) and value:
        return str(value[0])
    return None


class ToolPolicyEnforcer:
    """Stateful per-session companion to an immutable :class:`ToolPolicy`."""

    __slots__ = ("policy", "_calls", "_lock")

    def __init__(self, policy: ToolPolicy) -> None:
        self.policy = policy
        self._calls = 0
        self._lock = threading.Lock()

    @property
    def calls(self) -> int:
        with self._lock:
            return self._calls

    def check(self, tool_name: str, arguments: Mapping[str, Any]) -> str | None:
        """Return a denial reason, or ``None`` when the call is permitted.

        The call budget is consumed last, so a call refused on other grounds does
        not spend it.
        """

        policy = self.policy
        if policy.allow_tools is not None and tool_name not in policy.allow_tools:
            return f"tool {tool_name!r} is not in this session's allowlist"

        if policy.fs_roots:
            raw_path = arguments.get("path")
            if raw_path is not None:
                candidate = PurePosixPath(str(raw_path))
                resolved = PurePosixPath(*_normalize(candidate.parts))
                if not any(
                    resolved == PurePosixPath(root)
                    or resolved.is_relative_to(PurePosixPath(root))
                    for root in policy.fs_roots
                ):
                    return f"path {str(raw_path)!r} is outside the permitted roots"

        command = _first_token(arguments.get("cmd"))
        if command is not None:
            if policy.command_deny and command in policy.command_deny:
                return f"command {command!r} is denied by policy"
            if policy.command_allow and command not in policy.command_allow:
                return f"command {command!r} is not in this session's allowlist"

        if policy.max_calls is not None:
            with self._lock:
                if self._calls >= policy.max_calls:
                    return f"session exceeded max_calls={policy.max_calls} tool calls"
                self._calls += 1
        return None
