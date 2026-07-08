"""AgentParam: system :class:`~rath.session.session.Session` plus LLM prefs.

See :class:`~rath.llm.Provider`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Mapping

from rath.llm.provider import Provider
from rath.memory.abc import MemoryStore
from rath.session.session import Session


def resolve_provider_arg(
    provider: Provider | str | None = None,
    *,
    model: str | None = None,
    base: Provider | None = None,
) -> Provider:
    """Normalize a ``.to()``-style provider argument to a concrete ``Provider``.

    Shared by :meth:`AgentParam.to`, :meth:`Workflow.to`, and ``Session.to``:

    - a :class:`Provider` instance is used as-is (with ``model`` overlaid when
      given and its own model is unset);
    - a ``str`` is treated as a config provider **name** and resolved lazily via
      :meth:`Provider.from_config`;
    - ``None`` with ``model=`` builds ``Provider(model=...)``, or overlays
      ``model`` onto ``base`` when a base provider is supplied.

    Raises :class:`TypeError` for other types and :class:`ValueError` when there
    is nothing to build a provider from.
    """
    if isinstance(provider, Provider):
        if model is not None and provider.model is None:
            return replace(provider, model=model)
        return provider
    if isinstance(provider, str):
        overrides: dict[str, Any] = {}
        if model is not None:
            overrides["model"] = model
        return Provider.from_config(provider, **overrides)
    if provider is not None:
        raise TypeError(
            "provider must be a Provider, a config name (str), or None; "
            f"got {type(provider).__name__}"
        )
    # provider is None
    if base is not None:
        return replace(base, model=model) if model is not None else base
    if model is not None:
        return Provider(model=model)
    raise ValueError("nothing to bind: pass a Provider, provider=<name>, or model=")


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

    def to(
        self,
        target: Provider | None = None,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> "AgentParam":
        """Rebind this param's :class:`Provider` (chainable, returns ``self``).

        Type-dispatched, mirroring ``Session.to`` for sandboxes:

        - ``ap.to(Provider(...))`` — bind an explicit provider (positional);
        - ``ap.to(provider="name")`` — resolve a config preset lazily;
        - ``ap.to(model="m")`` — overlay just the model on the current provider.

        The positional argument accepts only a :class:`Provider`; a bare string
        is rejected because — unlike ``Session.to("local")`` (a sandbox backend
        name) — the LLM path has no unambiguous string form. Use
        ``provider="name"`` for a config preset instead.
        """
        if not isinstance(target, (Provider, type(None))):
            raise TypeError(
                "AgentParam.to() positional argument must be a Provider; "
                'use provider="name" for a config preset'
            )
        if target is not None and provider is not None:
            raise ValueError(
                "pass either a Provider positionally or provider=, not both"
            )
        if target is None and provider is None and model is None:
            raise ValueError(
                "nothing to bind: pass a Provider, provider=<name>, or model="
            )
        arg: Provider | str | None = target if target is not None else provider
        self.provider = resolve_provider_arg(arg, model=model, base=self.provider)
        return self

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
