"""Identity, tenancy, trust, and provenance contracts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum

from rath._json import JSONValue, freeze_mapping

__all__ = [
    "Principal",
    "PrincipalKind",
    "Provenance",
    "SecurityContext",
    "TrustLevel",
]


class PrincipalKind(str, Enum):
    USER = "user"
    SERVICE = "service"
    SYSTEM = "system"


class TrustLevel(str, Enum):
    UNTRUSTED = "untrusted"
    TRUSTED = "trusted"
    SYSTEM = "system"


def _required(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


@dataclass(frozen=True, slots=True)
class Principal:
    """Authenticated caller identity detached from transport concerns."""

    id: str
    kind: PrincipalKind
    claims: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required(self.id, field_name="principal.id"))
        object.__setattr__(
            self,
            "claims",
            freeze_mapping(self.claims, field="principal.claims"),
        )


@dataclass(frozen=True, slots=True)
class SecurityContext:
    """Run-scoped identity and tenant boundary."""

    principal: Principal
    tenant_id: str
    project_id: str | None = None
    grants: frozenset[str] = field(default_factory=frozenset)
    attributes: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tenant_id",
            _required(self.tenant_id, field_name="tenant_id"),
        )
        if self.project_id is not None:
            object.__setattr__(
                self,
                "project_id",
                _required(self.project_id, field_name="project_id"),
            )
        object.__setattr__(
            self,
            "grants",
            frozenset(_required(item, field_name="grant") for item in self.grants),
        )
        object.__setattr__(
            self,
            "attributes",
            freeze_mapping(self.attributes, field="security.attributes"),
        )

    @classmethod
    def local(
        cls,
        *,
        grants: Iterable[str] = ("trusted_host",),
    ) -> "SecurityContext":
        """Create the explicit trusted-process context for embedded local mode."""
        return cls(
            principal=Principal(
                id="local-process",
                kind=PrincipalKind.SYSTEM,
                claims={"mode": "embedded"},
            ),
            tenant_id="local",
            grants=frozenset(grants),
            attributes={"deployment_mode": "embedded"},
        )

    def has_grant(self, grant: str) -> bool:
        return grant in self.grants


@dataclass(frozen=True, slots=True)
class Provenance:
    """Origin metadata carried by untrusted and trusted content."""

    source_type: str
    source_id: str
    producer: str | None = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_type",
            _required(self.source_type, field_name="source_type"),
        )
        object.__setattr__(
            self,
            "source_id",
            _required(self.source_id, field_name="source_id"),
        )
        object.__setattr__(
            self,
            "metadata",
            freeze_mapping(self.metadata, field="provenance.metadata"),
        )
