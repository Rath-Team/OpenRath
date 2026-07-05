"""Workflow base type: assigns ``AgentParam`` attributes and orchestrates sessions."""

from __future__ import annotations

from typing import Any

from rath.flow.agent_param import AgentParam
from rath.llm.provider import Provider
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

    __slots__ = ("_agents", "_children", "description")

    _agents: dict[str, AgentParam]
    _children: dict[str, "Workflow"]
    description: str

    def __init__(self, description: str = "") -> None:
        object.__setattr__(self, "_agents", {})
        object.__setattr__(self, "_children", {})
        self.description = description

    def __setattr__(self, name: str, value: Any) -> None:
        # torch.nn.Module-like child registration: AgentParam leaves go into
        # _agents; nested Workflow/Agent children go into _children so
        # compile() can walk a real module tree (see P5).
        if isinstance(value, AgentParam):
            agents: dict[str, AgentParam] = object.__getattribute__(self, "_agents")
            agents[name] = value
        elif isinstance(value, Workflow):
            children: dict[str, Workflow] = object.__getattribute__(self, "_children")
            children[name] = value
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        object.__getattribute__(self, "_agents").pop(name, None)
        object.__getattribute__(self, "_children").pop(name, None)
        super().__delattr__(name)

    def named_agents(self) -> tuple[tuple[str, AgentParam], ...]:
        """Agent params registered directly on this workflow (sorted by name)."""

        agents: dict[str, AgentParam] = object.__getattribute__(self, "_agents")
        return tuple(sorted(agents.items(), key=lambda x: x[0]))

    def named_children(self) -> tuple[tuple[str, "Workflow"], ...]:
        """Nested ``Workflow``/``Agent`` children registered by attribute (sorted)."""

        children: dict[str, Workflow] = object.__getattribute__(self, "_children")
        return tuple(sorted(children.items(), key=lambda x: x[0]))

    def modules(self) -> "list[Workflow]":
        """This workflow followed by every descendant (pre-order, depth-first)."""

        out: list[Workflow] = [self]
        for _name, child in self.named_children():
            out.extend(child.modules())
        return out

    def to(
        self,
        target: Provider | None = None,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> "Workflow":
        """Rebind the provider on **every** registered ``AgentParam`` (chainable).

        Fans :meth:`AgentParam.to` out to each agent from :meth:`named_agents`,
        so ``workflow.to(Provider(...))`` / ``workflow.to(provider="name")`` /
        ``workflow.to(model="m")`` apply uniformly. A workflow with no agents is
        a no-op. A bare positional string is rejected (same rule as
        :meth:`AgentParam.to`).
        """
        agents: dict[str, AgentParam] = object.__getattribute__(self, "_agents")
        for ap in agents.values():
            ap.to(target, provider=provider, model=model)
        return self

    def forward(self, session: Session) -> Session:
        """Subclasses orchestrate Sessions (blocking)."""

        raise NotImplementedError

    def __call__(self, session: Session) -> Session:
        # Before forward, join any in-flight lazy materialization so
        # ``chunk_table`` is readable when ``forward`` runs.
        if session._pending is not None:
            session.synchronize()
        return self.forward(session)

    def __repr__(self) -> str:
        cls_name = type(self).__name__
        entries = list(self.named_agents()) + list(self.named_children())
        if not entries:
            return f"{cls_name}()"
        lines = [f"{cls_name}("]
        for child_name, node in entries:
            sub = _indent_child_module_repr(repr(node), 2)
            lines.append(f"  ({child_name}): {sub}")
        lines.append(")")
        return "\n".join(lines)

    __str__ = __repr__


__all__ = ["Workflow"]
