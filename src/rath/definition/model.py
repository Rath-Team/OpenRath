"""Versioned workflow-definition and executable-plan value objects."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID

from rath._json import JSONValue, freeze_mapping, thaw_json

__all__ = [
    "EdgeSpec",
    "EffectClass",
    "ExecutionPlan",
    "NodeKind",
    "NodeSpec",
    "ProviderResource",
    "ResourceManifestV2",
    "RetryPolicy",
    "WorkflowDefinition",
]


class EffectClass(str, Enum):
    NONE = "none"
    READ_ONLY = "read_only"
    IDEMPOTENT = "idempotent"
    NON_IDEMPOTENT = "non_idempotent"


class NodeKind(str, Enum):
    STEP = "step"
    ROUTER = "router"
    OPAQUE = "opaque"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 1
    base_seconds: float = 0.25
    max_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_seconds <= 0:
            raise ValueError("base_seconds must be greater than zero")
        if self.max_seconds < self.base_seconds:
            raise ValueError("max_seconds must be greater than or equal to base_seconds")

    def to_dict(self) -> dict[str, object]:
        return {
            "max_attempts": self.max_attempts,
            "base_seconds": self.base_seconds,
            "max_seconds": self.max_seconds,
        }


@dataclass(frozen=True, slots=True)
class NodeSpec:
    id: str
    kind: NodeKind
    handler: str
    is_async: bool
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    effects: EffectClass = EffectClass.NON_IDEMPOTENT
    idempotency_key: str | None = None
    timeout_seconds: float | None = None
    checkpoint: bool = True
    successors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("node id must not be empty")
        if not self.handler.strip():
            raise ValueError("node handler must not be empty")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("node timeout_seconds must be greater than zero")
        if (
            self.effects is EffectClass.NON_IDEMPOTENT
            and self.retry.max_attempts > 1
            and not self.idempotency_key
        ):
            raise ValueError(
                "non-idempotent retries require a stable idempotency key"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "handler": self.handler,
            "is_async": self.is_async,
            "retry": self.retry.to_dict(),
            "effects": self.effects.value,
            "idempotency_key": self.idempotency_key,
            "timeout_seconds": self.timeout_seconds,
            "checkpoint": self.checkpoint,
            "successors": list(self.successors),
        }


@dataclass(frozen=True, slots=True)
class EdgeSpec:
    source: str
    target: str

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "target": self.target}


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    id: UUID
    name: str
    version: str
    entrypoint: str
    nodes: tuple[NodeSpec, ...]
    edges: tuple[EdgeSpec, ...]
    input_schema: Mapping[str, JSONValue] = field(default_factory=dict)
    state_schema: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "input_schema",
            freeze_mapping(self.input_schema, field="definition.input_schema"),
        )
        object.__setattr__(
            self,
            "state_schema",
            freeze_mapping(self.state_schema, field="definition.state_schema"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "name": self.name,
            "version": self.version,
            "entrypoint": self.entrypoint,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "input_schema": thaw_json(self.input_schema),
            "state_schema": thaw_json(self.state_schema),
        }


@dataclass(frozen=True, slots=True)
class ProviderResource:
    path: str
    provider_kind: str
    model: str | None
    has_memory: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "provider_kind": self.provider_kind,
            "model": self.model,
            "has_memory": self.has_memory,
        }


@dataclass(frozen=True, slots=True)
class ResourceManifestV2:
    providers: tuple[ProviderResource, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "providers": [provider.to_dict() for provider in self.providers],
        }


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    id: UUID
    definition_hash: str
    revision_id: UUID
    definition: WorkflowDefinition
    nodes: tuple[NodeSpec, ...]
    resources: ResourceManifestV2
    policy_manifest: Mapping[str, JSONValue]
    durable: bool
    compatibility_issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_manifest",
            freeze_mapping(self.policy_manifest, field="plan.policy_manifest"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "definition_hash": self.definition_hash,
            "revision_id": str(self.revision_id),
            "definition": self.definition.to_dict(),
            "nodes": [node.to_dict() for node in self.nodes],
            "resources": self.resources.to_dict(),
            "policy_manifest": thaw_json(self.policy_manifest),
            "durable": self.durable,
            "compatibility_issues": list(self.compatibility_issues),
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

