"""Public :mod:`rath.backend` API: backends, tool types, registry, concurrency helpers."""

from __future__ import annotations

from rath.backend import local as _local  # noqa: F401
from rath.backend.abc import Backend, BackendSandbox, BackendSandboxSpec
from rath.backend.capabilities import (
    BackendCapability,
    Capabilities,
    IsolationLevel,
)
from rath.backend.errors import (
    BackendError,
    BackendNotFound,
    BackendSandboxClosed,
    UnsupportedBackendTool,
)
from rath.backend.registry import (
    current,
    get,
    get_class,
    is_available,
    list_names,
    preferred,
    register,
    set_default,
)
from rath.backend.results import (
    CodeResult,
    CommandResult,
    FileContent,
    FileEntries,
    FileEntry,
    FileWriteResult,
    ToolExecutionFailure,
    ToolResult,
)
from rath.backend.stream import Event, Future, Stream
from rath.backend.tool_types import (
    BackendTool,
    BackendToolCodeRun,
    BackendToolCommandRun,
    BackendToolFilesExists,
    BackendToolFilesList,
    BackendToolFilesRead,
    BackendToolFilesWrite,
)

try:
    from rath.backend import opensandbox as _opensandbox  # noqa: F401
except ImportError:  # pragma: no cover -- optional ``opensandbox`` extra
    pass

__all__ = [
    "Backend",
    "BackendSandbox",
    "BackendSandboxSpec",
    "BackendTool",
    "BackendToolCommandRun",
    "BackendToolFilesRead",
    "BackendToolFilesWrite",
    "BackendToolFilesList",
    "BackendToolFilesExists",
    "BackendToolCodeRun",
    "ToolResult",
    "ToolExecutionFailure",
    "CommandResult",
    "FileContent",
    "FileEntry",
    "FileEntries",
    "FileWriteResult",
    "CodeResult",
    "BackendCapability",
    "Capabilities",
    "IsolationLevel",
    "BackendError",
    "BackendNotFound",
    "BackendSandboxClosed",
    "UnsupportedBackendTool",
    "Stream",
    "Event",
    "Future",
    "register",
    "list_names",
    "get",
    "get_class",
    "is_available",
    "preferred",
    "set_default",
    "current",
]
