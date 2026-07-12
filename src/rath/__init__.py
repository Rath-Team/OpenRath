"""OpenRath: sandbox backends, LLM clients, and composable flow.

Sandbox dispatch uses :class:`~rath.backend.tool_types.BackendTool`. The session loop
uses :class:`~rath.flow.tool.FlowToolCall` as the flow-layer tool abstraction.

Import submodules explicitly, e.g. ``rath.flow.agent_param``; ``rath.session`` is
lazy-loaded via :func:`__getattr__`.

Persistent configuration (LLM providers, MCP servers) lives in
``~/.openrath/config.json`` — see :mod:`rath.config`. Environment variables
(``OPENAI_API_KEY`` etc.) continue to work and take precedence over the
config file; OpenRath no longer auto-loads ``.env``, so users wanting that
behavior should source it themselves before launching their script.
"""

from __future__ import annotations

import importlib
from typing import Any

from rath import (
    backend,
    flow,
    memory,
)

__all__ = ["backend", "benchmark", "env", "flow", "memory", "session", "training"]


def __getattr__(name: str) -> Any:
    """Lazy-load heavier subpackages on first attribute access."""
    if name == "benchmark":
        return importlib.import_module(f"{__name__}.benchmark")
    if name == "env":
        return importlib.import_module(f"{__name__}.env")
    if name == "session":
        return importlib.import_module(f"{__name__}.session")
    if name == "training":
        return importlib.import_module(f"{__name__}.training")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
