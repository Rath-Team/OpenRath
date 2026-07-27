"""Pluggable Agent Server authentication."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rath.security import SecurityContext

__all__ = ["AuthProvider", "StaticTokenAuth"]


@runtime_checkable
class AuthProvider(Protocol):
    async def authenticate(self, authorization: str | None) -> SecurityContext | None: ...


class StaticTokenAuth:
    """Reference bearer-token provider for self-hosted deployments and tests."""

    def __init__(self, tokens: dict[str, SecurityContext]) -> None:
        if not tokens:
            raise ValueError("at least one authentication token is required")
        self._tokens = dict(tokens)

    async def authenticate(self, authorization: str | None) -> SecurityContext | None:
        if not authorization or not authorization.startswith("Bearer "):
            return None
        return self._tokens.get(authorization.removeprefix("Bearer ").strip())

