"""Sync and native-async clients for the Agent Server resource API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

import httpx

__all__ = ["AsyncRemoteClient", "RemoteClient"]


class RemoteClient:
    def __init__(self, base_url: str, *, token: str, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    def create_run(
        self,
        *,
        assistant_id: str,
        session_id: str,
        state: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        response = self._client.post(
            "/v1/runs",
            json={
                "assistant_id": assistant_id,
                "session_id": session_id,
                "state": state or {},
            },
            headers=headers,
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def get_run(self, run_id: str) -> dict[str, Any]:
        response = self._client.get(f"/v1/runs/{run_id}")
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def close(self) -> None:
        self._client.close()


class AsyncRemoteClient:
    def __init__(self, base_url: str, *, token: str, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    async def create_run(
        self,
        *,
        assistant_id: str,
        session_id: str,
        state: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        response = await self._client.post(
            "/v1/runs",
            json={
                "assistant_id": assistant_id,
                "session_id": session_id,
                "state": state or {},
            },
            headers=headers,
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def get_run(self, run_id: str) -> dict[str, Any]:
        response = await self._client.get(f"/v1/runs/{run_id}")
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def events(self, run_id: str, *, after: int = 0) -> AsyncIterator[dict[str, Any]]:
        response = await self._client.get(
            f"/v1/runs/{run_id}/events",
            params={"after": after},
        )
        response.raise_for_status()
        for item in response.json()["items"]:
            yield item

    async def aclose(self) -> None:
        await self._client.aclose()
