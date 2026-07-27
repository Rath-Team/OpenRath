"""Starlette Agent Server exposing durable Run resources and SSE replay."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from rath._json import thaw_json
from rath.context import RunContext
from rath.errors import RathError
from rath.runtime import LocalRuntime, Run, RunStatus, SQLiteRunStore
from rath.security import SecurityContext
from rath.server.auth import AuthProvider

__all__ = ["AgentServer", "create_app"]


def _run_json(run: Run) -> dict[str, object]:
    return {
        "id": str(run.id),
        "plan_id": str(run.plan_id),
        "revision_id": str(run.revision_id),
        "session_id": str(run.session_id),
        "tenant_id": run.tenant_id,
        "status": run.status.value,
        "state": thaw_json(run.state),
        "next_nodes": list(run.next_nodes),
        "version": run.version,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


@dataclass(frozen=True, slots=True)
class _Assistant:
    id: str
    workflow: object
    revision_id: UUID


class AgentServer:
    def __init__(
        self,
        store: SQLiteRunStore,
        runtime: LocalRuntime,
        *,
        auth: AuthProvider,
    ) -> None:
        self.store = store
        self.runtime = runtime
        self.auth = auth
        self.assistants: dict[str, _Assistant] = {}
        self.app = create_app(self)

    def register_assistant(
        self,
        assistant_id: str,
        workflow: object,
        *,
        revision_id: UUID,
    ) -> None:
        if not assistant_id:
            raise ValueError("assistant_id is required")
        self.runtime.register(workflow, revision_id=revision_id)
        self.assistants[assistant_id] = _Assistant(
            id=assistant_id,
            workflow=workflow,
            revision_id=revision_id,
        )


def create_app(server: AgentServer) -> Starlette:
    async def authenticate(
        request: Request,
    ) -> tuple[SecurityContext | None, JSONResponse | None]:
        context = await server.auth.authenticate(request.headers.get("authorization"))
        if context is None:
            return None, JSONResponse(
                {"error": {"code": "security.unauthenticated", "message": "unauthenticated"}},
                status_code=401,
            )
        return context, None

    async def live(request: Request) -> Response:
        return JSONResponse({"status": "ok"})

    async def ready(request: Request) -> Response:
        try:
            server.store.list_runs(tenant_id="__readiness__")
        except Exception:
            return JSONResponse({"status": "not_ready"}, status_code=503)
        return JSONResponse({"status": "ready"})

    async def info(request: Request) -> Response:
        return JSONResponse(
            {
                "name": "openrath-agent-server",
                "api_version": "v1",
                "capabilities": ["runs", "events", "sse", "interrupts"],
            }
        )

    async def list_assistants(request: Request) -> Response:
        context, error = await authenticate(request)
        if error:
            return error
        assert context is not None
        return JSONResponse(
            {
                "items": [
                    {"id": item.id, "revision_id": str(item.revision_id)}
                    for item in server.assistants.values()
                ]
            }
        )

    async def create_run(request: Request) -> Response:
        context, error = await authenticate(request)
        if error:
            return error
        assert context is not None
        try:
            body = await request.json()
            assistant = server.assistants[str(body["assistant_id"])]
            session_id = UUID(str(body["session_id"]))
            run_context = RunContext(
                security=context,
                revision_id=assistant.revision_id,
            )
            run = server.runtime.submit(
                assistant.workflow,
                session_id=session_id,
                context=run_context,
                state=body.get("state") or {},
                idempotency_key=request.headers.get("idempotency-key"),
            )
            return JSONResponse(_run_json(run), status_code=201)
        except KeyError as exc:
            return JSONResponse(
                {"error": {"code": "request.invalid_argument", "message": str(exc)}},
                status_code=400,
            )
        except (ValueError, TypeError) as exc:
            return JSONResponse(
                {"error": {"code": "request.invalid_argument", "message": str(exc)}},
                status_code=400,
            )
        except RathError as exc:
            return JSONResponse({"error": exc.to_dict()}, status_code=409)

    async def get_run(request: Request) -> Response:
        context, error = await authenticate(request)
        if error:
            return error
        assert context is not None
        try:
            run = server.store.get_run(UUID(request.path_params["run_id"]))
        except (KeyError, ValueError):
            return JSONResponse(
                {"error": {"code": "resource.not_found", "message": "run not found"}},
                status_code=404,
            )
        if run.tenant_id != context.tenant_id:
            return JSONResponse(
                {"error": {"code": "resource.not_found", "message": "run not found"}},
                status_code=404,
            )
        return JSONResponse(_run_json(run))

    async def cancel_run(request: Request) -> Response:
        context, error = await authenticate(request)
        if error:
            return error
        assert context is not None
        try:
            run = server.store.get_run(UUID(request.path_params["run_id"]))
            if run.tenant_id != context.tenant_id:
                raise KeyError
            cancelled = server.store.transition_run(
                run.id,
                expected_version=run.version,
                target=RunStatus.CANCELLED,
            )
            return JSONResponse(_run_json(cancelled))
        except (KeyError, ValueError):
            return JSONResponse(
                {"error": {"code": "resource.not_found", "message": "run not found"}},
                status_code=404,
            )
        except RathError as exc:
            return JSONResponse({"error": exc.to_dict()}, status_code=409)

    async def events(request: Request) -> Response:
        context, error = await authenticate(request)
        if error:
            return error
        assert context is not None
        try:
            run_id = UUID(request.path_params["run_id"])
            run = server.store.get_run(run_id)
            if run.tenant_id != context.tenant_id:
                raise KeyError
        except (KeyError, ValueError):
            return JSONResponse(
                {"error": {"code": "resource.not_found", "message": "run not found"}},
                status_code=404,
            )
        after = int(request.query_params.get("after", "0"))
        items = [
            {
                "id": str(event.sequence),
                "run_id": str(event.run_id),
                "sequence": event.sequence,
                "type": event.type,
                "time": event.created_at.isoformat(),
                "data": thaw_json(event.data),
            }
            for event in server.store.list_run_events(run_id)
            if event.sequence > after
        ]
        return JSONResponse({"items": items})

    async def stream(request: Request) -> Response:
        response = await events(request)
        if response.status_code != 200:
            return response
        payload = json.loads(bytes(response.body))

        async def generate() -> AsyncIterator[str]:
            for item in payload["items"]:
                yield f"id: {item['sequence']}\nevent: {item['type']}\ndata: {json.dumps(item, separators=(',', ':'))}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    return Starlette(
        routes=[
            Route("/health/live", live),
            Route("/health/ready", ready),
            Route("/info", info),
            Route("/v1/assistants", list_assistants),
            Route("/v1/runs", create_run, methods=["POST"]),
            Route("/v1/runs/{run_id}", get_run),
            Route("/v1/runs/{run_id}/cancel", cancel_run, methods=["POST"]),
            Route("/v1/runs/{run_id}/events", events),
            Route("/v1/runs/{run_id}/stream", stream),
        ]
    )
