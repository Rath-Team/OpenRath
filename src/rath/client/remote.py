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

    def create_session(self) -> dict[str, Any]:
        response = self._client.post("/v1/sessions", json={})
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def create_assistant(
        self, *, assistant_id: str, template_id: str
    ) -> dict[str, Any]:
        response = self._client.post(
            "/v1/assistants",
            json={"id": assistant_id, "template_id": template_id},
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def list_assistants(self) -> tuple[dict[str, Any], ...]:
        response = self._client.get("/v1/assistants")
        response.raise_for_status()
        return tuple(cast(list[dict[str, Any]], response.json()["items"]))

    def store(
        self,
        operation: str,
        payload: dict[str, object],
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if operation not in {"put", "search", "delete"}:
            raise ValueError("store operation must be put, search, or delete")
        body = {
            "payload": payload,
            "user_id": user_id,
            "agent_id": agent_id,
            "session_id": session_id,
        }
        if operation == "search":
            response = self._client.post("/v1/store/search", json=body)
        elif operation == "put":
            response = self._client.post("/v1/store/items", json=body)
        else:
            response = self._client.request("DELETE", "/v1/store/items", json=body)
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def list_runs(self, *, limit: int = 50, after: str | None = None) -> dict[str, Any]:
        response = self._client.get("/v1/runs", params={"limit": limit, "after": after})
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        response = self._client.post(f"/v1/runs/{run_id}/cancel")
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def resume_run(self, run_id: str) -> dict[str, Any]:
        response = self._client.post(
            f"/v1/runs/{run_id}/resume", json={"confirm": True}
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def list_interrupts(
        self, *, pending_only: bool = True, limit: int = 50
    ) -> tuple[dict[str, Any], ...]:
        response = self._client.get(
            "/v1/interrupts",
            params={"pending": str(pending_only).lower(), "limit": limit},
        )
        response.raise_for_status()
        return tuple(cast(list[dict[str, Any]], response.json()["items"]))

    def decide_interrupt(
        self,
        interrupt_id: str,
        *,
        kind: str,
        reason: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        response = self._client.post(
            f"/v1/interrupts/{interrupt_id}/decision",
            json={"kind": kind, "reason": reason, "payload": payload or {}},
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def events(self, run_id: str, *, after: int = 0) -> tuple[dict[str, Any], ...]:
        response = self._client.get(
            f"/v1/runs/{run_id}/events", params={"after": after}
        )
        response.raise_for_status()
        return tuple(cast(list[dict[str, Any]], response.json()["items"]))

    def create_feedback(
        self,
        run_id: str,
        *,
        key: str,
        score: float | None = None,
        value: str | None = None,
    ) -> dict[str, Any]:
        response = self._client.post(
            "/v1/feedback",
            json={"run_id": run_id, "key": key, "score": score, "value": value},
        )
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

    async def create_session(self) -> dict[str, Any]:
        response = await self._client.post("/v1/sessions", json={})
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def create_assistant(
        self, *, assistant_id: str, template_id: str
    ) -> dict[str, Any]:
        response = await self._client.post(
            "/v1/assistants",
            json={"id": assistant_id, "template_id": template_id},
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def list_assistants(self) -> tuple[dict[str, Any], ...]:
        response = await self._client.get("/v1/assistants")
        response.raise_for_status()
        return tuple(cast(list[dict[str, Any]], response.json()["items"]))

    async def store(
        self,
        operation: str,
        payload: dict[str, object],
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if operation not in {"put", "search", "delete"}:
            raise ValueError("store operation must be put, search, or delete")
        body = {
            "payload": payload,
            "user_id": user_id,
            "agent_id": agent_id,
            "session_id": session_id,
        }
        if operation == "search":
            response = await self._client.post("/v1/store/search", json=body)
        elif operation == "put":
            response = await self._client.post("/v1/store/items", json=body)
        else:
            response = await self._client.request(
                "DELETE", "/v1/store/items", json=body
            )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def list_runs(
        self, *, limit: int = 50, after: str | None = None
    ) -> dict[str, Any]:
        response = await self._client.get(
            "/v1/runs", params={"limit": limit, "after": after}
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def cancel_run(self, run_id: str) -> dict[str, Any]:
        response = await self._client.post(f"/v1/runs/{run_id}/cancel")
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def resume_run(self, run_id: str) -> dict[str, Any]:
        response = await self._client.post(
            f"/v1/runs/{run_id}/resume", json={"confirm": True}
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def list_interrupts(
        self, *, pending_only: bool = True, limit: int = 50
    ) -> tuple[dict[str, Any], ...]:
        response = await self._client.get(
            "/v1/interrupts",
            params={"pending": str(pending_only).lower(), "limit": limit},
        )
        response.raise_for_status()
        return tuple(cast(list[dict[str, Any]], response.json()["items"]))

    async def decide_interrupt(
        self,
        interrupt_id: str,
        *,
        kind: str,
        reason: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        response = await self._client.post(
            f"/v1/interrupts/{interrupt_id}/decision",
            json={"kind": kind, "reason": reason, "payload": payload or {}},
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def create_feedback(
        self,
        run_id: str,
        *,
        key: str,
        score: float | None = None,
        value: str | None = None,
    ) -> dict[str, Any]:
        response = await self._client.post(
            "/v1/feedback",
            json={"run_id": run_id, "key": key, "score": score, "value": value},
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def events(
        self, run_id: str, *, after: int = 0
    ) -> AsyncIterator[dict[str, Any]]:
        response = await self._client.get(
            f"/v1/runs/{run_id}/events",
            params={"after": after},
        )
        response.raise_for_status()
        for item in response.json()["items"]:
            yield item

    async def aclose(self) -> None:
        await self._client.aclose()
