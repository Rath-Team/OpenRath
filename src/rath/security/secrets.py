"""Secret references and explicit resolution boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from rath.context import RunContext

__all__ = [
    "ResolvedSecret",
    "SecretRef",
    "SecretResolver",
]


@dataclass(frozen=True, slots=True)
class SecretRef:
    provider: str
    key: str
    version: str | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("secret provider must not be empty")
        if not self.key.strip():
            raise ValueError("secret key must not be empty")

    def __str__(self) -> str:
        version = f"@{self.version}" if self.version else ""
        return f"{self.provider}:{self.key}{version}"


@dataclass(frozen=True, slots=True, repr=False)
class ResolvedSecret:
    """Short-lived secret value whose representation is always redacted."""

    ref: SecretRef
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("resolved secret value must not be empty")

    def __repr__(self) -> str:
        return f"ResolvedSecret(ref={self.ref!s}, value=<redacted>)"

    def __str__(self) -> str:
        return f"<resolved-secret {self.ref!s}>"

    def reveal(self) -> str:
        """Return the value at the adapter boundary; callers must not log it."""
        return self.value


@runtime_checkable
class SecretResolver(Protocol):
    async def resolve(
        self,
        ref: SecretRef,
        *,
        context: RunContext,
    ) -> ResolvedSecret: ...
