"""Versioned external adapter specifications without resolved credentials."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from rath.definition import EffectClass
from rath.security import SecretRef, TrustLevel

__all__ = [
    "MemoryNamespace",
    "ProviderCapability",
    "ProviderSpec",
    "SandboxIsolation",
    "SandboxSpec",
    "ToolSpec",
]


class ProviderCapability(str, Enum):
    CHAT = "chat"
    STREAM = "stream"
    TOOLS = "tools"
    STRUCTURED_OUTPUT = "structured_output"
    EMBEDDING = "embedding"
    VISION = "vision"


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    id: str
    kind: str
    model: str
    credential: SecretRef | None = None
    capabilities: frozenset[ProviderCapability] = field(default_factory=frozenset)
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 60.0
    total_timeout_seconds: float = 120.0
    max_concurrency: int = 16

    def __post_init__(self) -> None:
        if not self.id or not self.kind or not self.model:
            raise ValueError("provider id, kind, and model are required")
        if (
            min(
                self.connect_timeout_seconds,
                self.read_timeout_seconds,
                self.total_timeout_seconds,
            )
            <= 0
        ):
            raise ValueError("provider timeouts must be positive")
        if self.max_concurrency < 1:
            raise ValueError("provider max_concurrency must be positive")


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    version: str
    input_schema: dict[str, object]
    output_schema: dict[str, object] | None = None
    effects: EffectClass = EffectClass.NON_IDEMPOTENT
    risk: Literal["low", "medium", "high", "critical"] = "high"
    timeout_seconds: float = 30.0
    max_output_bytes: int = 1024 * 1024
    requires_approval: bool = False

    def __post_init__(self) -> None:
        if not self.name or not self.version:
            raise ValueError("tool name and version are required")
        if self.timeout_seconds <= 0 or self.max_output_bytes <= 0:
            raise ValueError("tool budgets must be positive")
        if self.effects is EffectClass.NON_IDEMPOTENT and self.risk in {
            "high",
            "critical",
        }:
            object.__setattr__(self, "requires_approval", True)


class SandboxIsolation(str, Enum):
    TRUSTED_HOST = "trusted_host"
    LOCAL_CONTAINER = "local_container"
    REMOTE_CONTAINER = "remote_container"


@dataclass(frozen=True, slots=True)
class SandboxSpec:
    id: str
    isolation: SandboxIsolation
    image_digest: str | None = None
    cpu_limit: float | None = None
    memory_bytes: int | None = None
    disk_bytes: int | None = None
    process_limit: int | None = None
    network: Literal["deny", "allowlist", "unrestricted"] = "deny"
    allowed_hosts: frozenset[str] = field(default_factory=frozenset)
    ttl_seconds: int = 900

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("sandbox id is required")
        if self.ttl_seconds <= 0:
            raise ValueError("sandbox ttl_seconds must be positive")
        if (
            self.isolation is not SandboxIsolation.TRUSTED_HOST
            and not self.image_digest
        ):
            raise ValueError("container sandboxes require an immutable image_digest")
        if self.network == "allowlist" and not self.allowed_hosts:
            raise ValueError("network allowlist requires at least one host")


@dataclass(frozen=True, slots=True)
class MemoryNamespace:
    tenant_id: str
    user_id: str | None = None
    agent_id: str | None = None
    session_id: str | None = None
    trust: TrustLevel = TrustLevel.UNTRUSTED

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("memory namespace tenant_id is required")
