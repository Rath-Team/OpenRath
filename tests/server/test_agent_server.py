from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import httpx

from rath.adapters import MemoryExecutor
from rath.definition import EffectClass, step
from rath.flow import Workflow
from rath.runtime import InterruptKind, LocalRuntime, RunStatus, SQLiteRunStore
from rath.security import (
    LocalTrustedPolicy,
    Principal,
    PrincipalKind,
    SecurityContext,
)
from rath.server import AgentServer, StaticTokenAuth
from rath.session import Session


class _Echo(Workflow):
    @step(entry=True, effects=EffectClass.READ_ONLY)
    def echo(self, state, context):  # type: ignore[no-untyped-def]
        return {**state, "done": True}

    def forward(self, session: Session) -> Session:
        return session


class _Approval(Workflow):
    @step(entry=True, effects=EffectClass.NON_IDEMPOTENT)
    def approve(self, state, context):  # type: ignore[no-untyped-def]
        decision = context.interrupt(
            InterruptKind.APPROVAL,
            {"tool": "email.send"},
        )
        return {"decision": decision.kind.value}

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
            assert first.headers["x-request-id"]
            assert first.json()["request_id"]
            assert first.json()["trace_id"]
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
            assert (await client.get("/openapi.json")).status_code == 200
            assert (await client.get("/metrics")).status_code == 200

            session = await client.post("/v1/sessions", headers=headers)
            assert session.status_code == 201
            session_id = session.json()["id"]
            session_run = await client.post(
                f"/v1/sessions/{session_id}/runs",
                headers={"Authorization": "Bearer token"},
                json={"assistant_id": "echo", "state": {"value": 2}},
            )
            assert session_run.status_code == 201
            listed = await client.get("/v1/runs?limit=1", headers=headers)
            assert len(listed.json()["items"]) == 1
            assert listed.json()["next"] is not None
            assistant = await client.get("/v1/assistants/echo", headers=headers)
            assert assistant.status_code == 200
            alias = await client.post(
                "/v1/assistants",
                headers=headers,
                json={"id": "tenant-echo", "template_id": "echo"},
            )
            assert alias.status_code == 201
            assert alias.json()["kind"] == "alias"
            alias_run = await client.post(
                "/v1/runs",
                headers={"Authorization": "Bearer token"},
                json={
                    "assistant_id": "tenant-echo",
                    "session_id": str(uuid4()),
                    "state": {"value": 3},
                },
            )
            assert alias_run.status_code == 201
            listed_assistants = await client.get(
                "/v1/assistants", headers=headers
            )
            assert {item["id"] for item in listed_assistants.json()["items"]} == {
                "echo",
                "tenant-echo",
            }
            reconnected = await client.get(
                f"/v1/runs/{run_id}/stream",
                headers={**headers, "Last-Event-ID": "1"},
            )
            assert "id: 1\n" not in reconnected.text
            feedback = await client.post(
                "/v1/feedback",
                headers=headers,
                json={"run_id": run_id, "key": "quality", "score": 1},
            )
            assert feedback.status_code == 201
            assert feedback.headers["x-content-type-options"] == "nosniff"
            oversized = await client.post(
                "/v1/runs",
                headers={"Authorization": "Bearer token"},
                content=b"x" * (1024 * 1024 + 1),
            )
            assert oversized.status_code == 400

    asyncio.run(exercise())


def test_store_api_is_policy_governed_and_tenant_scoped(tmp_path: Path) -> None:
    import asyncio

    async def exercise() -> None:
        store = SQLiteRunStore(tmp_path / "store-api.db")
        runtime = LocalRuntime(store)
        local = SecurityContext.local()
        calls: list[tuple[str, str, dict[str, object]]] = []

        def memory_handler(operation, namespace, payload, context):  # type: ignore[no-untyped-def]
            calls.append((operation, namespace.tenant_id, dict(payload)))
            return {"operation": operation, "tenant_id": namespace.tenant_id}

        server = AgentServer(
            store,
            runtime,
            auth=StaticTokenAuth({"token": local}),
            memory_executor=MemoryExecutor(LocalTrustedPolicy()),
            memory_handler=memory_handler,
        )
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            headers = {"Authorization": "Bearer token"}
            response = await client.post(
                "/v1/store/search",
                headers=headers,
                json={"payload": {"query": "safe"}},
            )
            assert response.status_code == 200
            assert response.json()["result"]["tenant_id"] == "local"
            denied = await client.post(
                "/v1/store/search",
                headers=headers,
                json={"tenant_id": "other", "payload": {"query": "unsafe"}},
            )
            assert denied.status_code == 403
            assert calls == [("search", "local", {"query": "safe"})]

    asyncio.run(exercise())


def test_server_interrupt_inbox_and_decision_resume(tmp_path: Path) -> None:
    import asyncio

    async def exercise() -> None:
        store = SQLiteRunStore(tmp_path / "interrupt-api.db")
        runtime = LocalRuntime(store)
        tenant = SecurityContext(
            principal=Principal(id="reviewer", kind=PrincipalKind.USER),
            tenant_id="tenant",
        )
        server = AgentServer(
            store,
            runtime,
            auth=StaticTokenAuth({"token": tenant}),
        )
        server.register_assistant(
            "approval",
            _Approval(),
            revision_id=uuid4(),
        )
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            headers = {"Authorization": "Bearer token"}
            created = await client.post(
                "/v1/runs",
                headers=headers,
                json={
                    "assistant_id": "approval",
                    "session_id": str(uuid4()),
                },
            )
            assert created.status_code == 201
            waiting = runtime.work_once(worker_id="worker-1")
            assert waiting is not None and waiting.status is RunStatus.WAITING
            inbox = await client.get("/v1/interrupts", headers=headers)
            assert inbox.status_code == 200
            (interrupt,) = inbox.json()["items"]
            decided = await client.post(
                f"/v1/interrupts/{interrupt['id']}/decision",
                headers=headers,
                    json={
                        "kind": "approve",
                        "reason": "expected test operation",
                    },
            )
            assert decided.status_code == 200
            completed = runtime.work_once(worker_id="worker-2")
            assert completed is not None
            assert completed.status is RunStatus.SUCCEEDED
            assert completed.state["decision"] == "approve"

    asyncio.run(exercise())
