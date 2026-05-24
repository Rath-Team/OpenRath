"""Workflow base type: assigns ``AgentParam`` attributes and orchestrates sessions."""

from __future__ import annotations

from typing import Any

from rath.flow.agent_param import AgentParam
from rath.session.session import Session


def _indent_child_module_repr(body: str, spaces: int = 2) -> str:
    """Indent a child ``repr`` like ``torch.nn.Module`` (first line unindented)."""

    lines = body.split("\n")
    if len(lines) <= 1:
        return body
    first, *rest = lines
    pad = " " * spaces
    return first + "\n" + "\n".join(pad + line for line in rest)


class Workflow:
    """Collects attached ``AgentParam`` instances and subclasses run sessions here."""

    __slots__ = ("_agents",)

    _agents: dict[str, AgentParam]

    def __init__(self) -> None:
        object.__setattr__(self, "_agents", {})

    def __setattr__(self, name: str, value: Any) -> None:
        if isinstance(value, AgentParam):
            agents: dict[str, AgentParam] = object.__getattribute__(self, "_agents")
            agents[name] = value
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        agents = object.__getattribute__(self, "_agents")
        agents.pop(name, None)
        super().__delattr__(name)

    def named_agents(self) -> tuple[tuple[str, AgentParam], ...]:
        """Agent params registered via attribute assignment."""

        agents: dict[str, AgentParam] = object.__getattribute__(self, "_agents")
        return tuple(sorted(agents.items(), key=lambda x: x[0]))

    def forward(self, session: Session) -> Session:
        """Subclasses orchestrate Sessions (blocking)."""

        raise NotImplementedError

    def __call__(self, session: Session) -> Session:
        # Concurrency invariant 7: consuming a lazy session auto-joins its
        # in-flight materialization before ``forward`` reads ``chunk_table``.
        if session._pending is not None:
            session.synchronize()
        return self.forward(session)

    def __repr__(self) -> str:
        cls_name = type(self).__name__
        agents = self.named_agents()
        if not agents:
            return f"{cls_name}()"
        lines = [f"{cls_name}("]
        for child_name, agent in agents:
            sub = repr(agent)
            sub = _indent_child_module_repr(sub, 2)
            lines.append(f"  ({child_name}): {sub}")
        lines.append(")")
        return "\n".join(lines)

    __str__ = __repr__


__all__ = ["Workflow"]
