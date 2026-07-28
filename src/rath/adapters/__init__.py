"""Shared v2 adapter contracts."""

from rath.adapters.context import (
    AdapterRequestContext,
    merge_policy_constraints,
    with_policy_constraints,
)
from rath.adapters.memory import MemoryExecutor, MemoryHandler
from rath.adapters.provider import ProviderExecutor, ProviderHandler
from rath.adapters.sandbox import SandboxExecutor, SandboxHandler
from rath.adapters.schema import SchemaValidationError, validate_json
from rath.adapters.specs import (
    MemoryNamespace,
    ProviderCapability,
    ProviderSpec,
    SandboxIsolation,
    SandboxSpec,
    ToolSpec,
)
from rath.adapters.tool import (
    ApprovalGrant,
    ApprovalValidator,
    ToolExecutor,
    ToolHandler,
    ToolOutputTooLarge,
)

__all__ = [
    "AdapterRequestContext",
    "ApprovalGrant",
    "ApprovalValidator",
    "MemoryNamespace",
    "MemoryExecutor",
    "MemoryHandler",
    "merge_policy_constraints",
    "ProviderCapability",
    "ProviderExecutor",
    "ProviderHandler",
    "ProviderSpec",
    "SandboxIsolation",
    "SandboxExecutor",
    "SandboxHandler",
    "SandboxSpec",
    "SchemaValidationError",
    "ToolExecutor",
    "ToolHandler",
    "ToolOutputTooLarge",
    "ToolSpec",
    "validate_json",
    "with_policy_constraints",
]
