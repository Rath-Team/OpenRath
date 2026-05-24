"""Flow-layer tool abstraction: schema + :meth:`~FlowToolCall.__call__` execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from rath.session.session import Session

__all__ = ["FlowToolCall"]


class FlowToolCall(ABC):
    """User- or system-defined tool for the session loop (distinct from :class:`~rath.backend.tool_types.BackendTool`).

    Concurrency contract (used by the async session loop):

    - ``parallel_safe``: class attribute. ``True`` means the runtime may
      ``await`` this tool concurrently with other ``parallel_safe`` tools
      sharing a *different* :meth:`resource_key`. ``False`` means the
      runtime must run this tool serially with respect to every other tool
      in the same round. Built-in writes/exec tools default to ``False``;
      pure reads default to ``True``; user tools default to ``False`` and
      must opt-in explicitly.
    - :meth:`resource_key`: keys the runtime uses to serialize tools that
      touch the same resource. Same key → serial; different key → parallel.
      Default returns ``("global",)`` for non-parallel-safe tools so they
      pile up on one queue; ``("safe", name)`` for parallel-safe tools so
      they fan out freely.
    """

    parallel_safe: bool = False

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def description(self) -> str | None:
        return None

    @property
    @abstractmethod
    def parameters(self) -> Mapping[str, Any]:
        """JSON Schema object for OpenAI ``parameters``."""

    def resource_key(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
        """Return the resource-key the async runtime serializes on.

        Override for fs/exec tools to expose a meaningful key (path,
        sandbox handle, ...). Default partitions tools into one global
        serial lane for non-parallel-safe tools and a per-name lane for
        parallel-safe tools.
        """
        if self.parallel_safe:
            return ("safe", self.name)
        return ("global",)

    @abstractmethod
    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> Any:
        """Execute the tool. Sandbox tools may return :class:`~rath.backend.ToolResult` or ``bool``."""
