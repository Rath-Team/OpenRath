"""AgentParam: system :class:`~rath.session.session.Session` plus LLM prefs.

See :class:`~rath.llm.Provider`.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from rath.llm.provider import Provider
from rath.memory.abc import MemoryStore
from rath.session.session import Session


def _indent_child_module_repr(body: str, spaces: int = 2) -> str:
    """Indent a child ``repr`` like ``torch.nn.Module`` (first line unindented)."""

    lines = body.split("\n")
    if len(lines) <= 1:
        return body
    first, *rest = lines
    pad = " " * spaces
    return first + "\n" + "\n".join(pad + line for line in rest)


@dataclass(slots=True)
class AgentParam:
    """System session plus LLM options for ``run_session_loop``."""

    agent_session: Session
    provider: Provider
    memory: MemoryStore | None = None

    @property
    def data(self) -> Mapping[str, Any]:
        """Read-only mapping of underlying ``agent_session``, ``provider`` and ``memory``."""

        return MappingProxyType(
            {
                "agent_session": self.agent_session,
                "provider": self.provider,
                "memory": self.memory,
            }
        )

    def __repr__(self) -> str:
        name = type(self).__name__
        sess_body = repr(self.agent_session)
        sess_body = _indent_child_module_repr(sess_body, 2)
        lines = [
            f"{name}(",
            f"  (agent_session): {sess_body}",
            f"  (provider): {self.provider!s}",
        ]
        if self.memory is not None:
            mem_body = _indent_child_module_repr(repr(self.memory), 2)
            lines.append(f"  (memory): {mem_body}")
        lines.append(")")
        return "\n".join(lines)

    __str__ = __repr__


__all__ = ["AgentParam", "Provider"]
