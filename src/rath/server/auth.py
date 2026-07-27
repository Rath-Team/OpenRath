"""Pluggable Agent Server authentication."""

from __future__ import annotations

import hashlib
import hmac
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
        self._tokens = {
            hashlib.sha256(token.encode()).digest(): context
            for token, context in tokens.items()
        }

    async def authenticate(self, authorization: str | None) -> SecurityContext | None:
        if not authorization or not authorization.startswith("Bearer "):
            return None
        supplied = hashlib.sha256(
            authorization.removeprefix("Bearer ").strip().encode()
        ).digest()
        for expected, context in self._tokens.items():
            if hmac.compare_digest(supplied, expected):
                return context
        return None
