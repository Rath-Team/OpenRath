from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import httpx

from rath.definition import EffectClass, step
from rath.flow import Workflow
from rath.runtime import LocalRuntime, SQLiteRunStore
from rath.security import Principal, PrincipalKind, SecurityContext
from rath.server import AgentServer, StaticTokenAuth
from rath.session import Session


class _Echo(Workflow):
    @step(entry=True, effects=EffectClass.READ_ONLY)
    def echo(self, state, context):  # type: ignore[no-untyped-def]
        return {**state, "done": True}

    def forward(self, session: Session) -> Session:
        return session


def test_server_auth_tenant_idempotency_and_sse_sync(tmp_path: Path) -> None:
    import asyncio

    async def exercise() -> None:
        store = SQLiteRunStore(tmp_path / "runtime.db")
        runtime = LocalRuntime(store)
        tenant = SecurityContext(
            principal=Principal(id="user-1", kind=PrincipalKind.USER),
            tenant_id="tenant-1",
        )
        server = AgentServer(
            store,
            runtime,
            auth=StaticTokenAuth({"token": tenant}),
        )
        server.register_assistant("echo", _Echo(), revision_id=uuid4())
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            assert (await client.get("/v1/assistants")).status_code == 401
            headers = {
                "Authorization": "Bearer token",
                "Idempotency-Key": "req-1",
            }
            body = {
                "assistant_id": "echo",
                "session_id": str(uuid4()),
                "state": {"value": 1},
            }
            first = await client.post("/v1/runs", headers=headers, json=body)
            second = await client.post("/v1/runs", headers=headers, json=body)
            assert first.status_code == 201
            assert second.json()["id"] == first.json()["id"]
            runtime.work_once(worker_id="worker")
            run_id = first.json()["id"]
            fetched = await client.get(f"/v1/runs/{run_id}", headers=headers)
            assert fetched.json()["status"] == "succeeded"
            stream = await client.get(
                f"/v1/runs/{run_id}/stream?after=1",
                headers=headers,
            )
            assert stream.status_code == 200
            assert "run.checkpoint.created" in stream.text
            assert (await client.get("/health/ready")).status_code == 200

    asyncio.run(exercise())
