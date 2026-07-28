"""Starlette Agent Server exposing durable Run resources and SSE replay."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import Any, cast
from uuid import UUID, uuid4

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from rath._json import JSONValue, thaw_json
from rath.adapters import (
    AdapterRequestContext,
    MemoryExecutor,
    MemoryHandler,
    MemoryNamespace,
)
from rath.context import RunContext
from rath.errors import ErrorCode, RathError
from rath.runtime import (
    ApprovalDecision,
    ApprovalDecisionKind,
    Interrupt,
    LocalRuntime,
    Run,
    RunSignal,
    RunStatus,
    RunStore,
    SignalBus,
    SignalKind,
)
from rath.security import (
    AuditEvent,
    AuditKind,
    AuditSink,
    PolicyConstraints,
    SecurityContext,
    TrustLevel,
)
from rath.server.auth import AuthProvider
from rath.server.authorization import allows, project_allows
from rath.server.resources import ResourceStore, default_resource_store

__all__ = ["AgentServer", "create_app"]


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        requested = request.headers.get("x-request-id")
        try:
            request_id = str(UUID(requested)) if requested else str(uuid4())
        except ValueError:
            request_id = str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = response.headers.get(
            "Cache-Control", "no-store"
        )
        return cast(Response, response)


def _run_json(run: Run) -> dict[str, object]:
    context = thaw_json(run.context)
    correlation = context if isinstance(context, dict) else {}
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
        "priority": run.priority,
        "request_id": correlation.get("request_id"),
        "trace_id": correlation.get("trace_id"),
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


def _interrupt_json(value: Interrupt) -> dict[str, object]:
    return {
        "id": str(value.id),
        "run_id": str(value.run_id),
        "kind": value.kind.value,
        "request": thaw_json(value.request),
        "created_at": value.created_at.isoformat(),
        "expires_at": (
            value.expires_at.isoformat() if value.expires_at is not None else None
        ),
        "decision": (
            {
                "kind": value.decision.kind.value,
                "actor_id": value.decision.actor_id,
                "reason": value.decision.reason,
                "payload": thaw_json(value.decision.payload),
            }
            if value.decision is not None
            else None
        ),
        "decided_at": (
            value.decided_at.isoformat() if value.decided_at is not None else None
        ),
    }


@dataclass(frozen=True, slots=True)
class _Assistant:
    id: str
    workflow: object
    revision_id: UUID


def _openapi_document(
    package_version: str, *, store_enabled: bool
) -> dict[str, object]:
    secured: list[dict[str, list[object]]] = [{"bearerAuth": []}]
    error_content = {
        "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}
    }

    def operation(
        operation_id: str,
        summary: str,
        *,
        action: str | None = None,
        success: str = "200",
        response_schema: str | None = None,
        request_schema: str | None = None,
        parameters: list[dict[str, object]] | None = None,
        media_type: str = "application/json",
    ) -> dict[str, object]:
        success_schema: dict[str, object] = (
            {"$ref": f"#/components/schemas/{response_schema}"}
            if response_schema
            else {"type": "object"}
        )
        value: dict[str, object] = {
            "operationId": operation_id,
            "summary": summary,
            "x-openrath-stability": "beta",
            "x-openrath-action": action,
            "security": secured if action is not None else [],
            "responses": {
                success: {
                    "description": "Success",
                    "content": {media_type: {"schema": success_schema}},
                },
                "400": {"description": "Invalid request", "content": error_content},
                "401": {"description": "Unauthenticated", "content": error_content},
                "403": {"description": "Forbidden", "content": error_content},
                "404": {"description": "Not found", "content": error_content},
                "409": {"description": "Conflict", "content": error_content},
                "429": {"description": "Resource exhausted", "content": error_content},
            },
        }
        if request_schema is not None:
            value["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "$ref": f"#/components/schemas/{request_schema}",
                        }
                    }
                },
            }
        if parameters:
            value["parameters"] = parameters
        return value

    def path_parameter(name: str) -> dict[str, object]:
        schema: dict[str, object] = {"type": "string"}
        if name in {"session_id", "run_id", "interrupt_id"}:
            schema["format"] = "uuid"
        return {
            "name": name,
            "in": "path",
            "required": True,
            "schema": schema,
        }

    cursor_parameters = [
        {
            "name": "after",
            "in": "query",
            "required": False,
            "schema": {"type": "string"},
        },
        {
            "name": "limit",
            "in": "query",
            "required": False,
            "schema": {"type": "integer", "minimum": 1, "maximum": 200},
        },
    ]
    paths: dict[str, object] = {
        "/health/live": {
            "get": operation("live", "Process liveness", response_schema="Health")
        },
        "/health/ready": {
            "get": operation("ready", "Dependency readiness", response_schema="Health")
        },
        "/info": {
            "get": operation("info", "Server capabilities", response_schema="Info")
        },
        "/metrics": {
            "get": operation(
                "metrics",
                "Prometheus metrics",
                action="metrics.read",
                media_type="text/plain",
            )
        },
        "/v1/assistants": {
            "get": operation(
                "listAssistants",
                "List deployment templates and tenant aliases",
                action="assistant.read",
                response_schema="ItemPage",
            ),
            "post": operation(
                "createAssistantAlias",
                "Create a tenant assistant alias",
                action="assistant.create",
                success="201",
                request_schema="CreateAssistantRequest",
                response_schema="Assistant",
            ),
        },
        "/v1/assistants/{assistant_id}": {
            "get": operation(
                "getAssistant",
                "Get an assistant template or alias",
                action="assistant.read",
                response_schema="Assistant",
                parameters=[path_parameter("assistant_id")],
            )
        },
        "/v1/sessions": {
            "post": operation(
                "createSession",
                "Create a durable session",
                action="session.create",
                success="201",
                response_schema="Session",
            )
        },
        "/v1/sessions/{session_id}": {
            "get": operation(
                "getSession",
                "Get a durable session",
                action="session.read",
                response_schema="Session",
                parameters=[path_parameter("session_id")],
            )
        },
        "/v1/sessions/{session_id}/runs": {
            "post": operation(
                "createSessionRun",
                "Create a run in an existing session",
                action="run.create",
                success="201",
                request_schema="CreateSessionRunRequest",
                response_schema="Run",
                parameters=[path_parameter("session_id")],
            )
        },
        "/v1/runs": {
            "get": operation(
                "listRuns",
                "List runs by cursor",
                action="run.read",
                response_schema="ItemPage",
                parameters=cursor_parameters,
            ),
            "post": operation(
                "createRun",
                "Create a durable run",
                action="run.create",
                success="201",
                request_schema="CreateRunRequest",
                response_schema="Run",
            ),
        },
        "/v1/runs/{run_id}": {
            "get": operation(
                "getRun",
                "Get a durable run",
                action="run.read",
                response_schema="Run",
                parameters=[path_parameter("run_id")],
            )
        },
        "/v1/runs/{run_id}/cancel": {
            "post": operation(
                "cancelRun",
                "Cancel a run",
                action="run.cancel",
                response_schema="Run",
                parameters=[path_parameter("run_id")],
            )
        },
        "/v1/runs/{run_id}/resume": {
            "post": operation(
                "resumeRun",
                "Resume a run requiring operator review",
                action="run.resume",
                request_schema="ResumeRunRequest",
                response_schema="Run",
                parameters=[path_parameter("run_id")],
            )
        },
        "/v1/runs/{run_id}/events": {
            "get": operation(
                "listRunEvents",
                "Replay ordered durable run events",
                action="run.read",
                response_schema="ItemPage",
                parameters=[path_parameter("run_id"), *cursor_parameters],
            )
        },
        "/v1/runs/{run_id}/stream": {
            "get": operation(
                "streamRunEvents",
                "Stream ordered run events with cursor resume",
                action="run.read",
                media_type="text/event-stream",
                parameters=[path_parameter("run_id"), *cursor_parameters],
            )
        },
        "/v1/interrupts": {
            "get": operation(
                "listInterrupts",
                "List pending durable interrupts",
                action="interrupt.read",
                response_schema="ItemPage",
                parameters=cursor_parameters,
            )
        },
        "/v1/interrupts/{interrupt_id}/decision": {
            "post": operation(
                "decideInterrupt",
                "Submit a durable interrupt decision",
                action="interrupt.decide",
                request_schema="InterruptDecisionRequest",
                response_schema="Run",
                parameters=[path_parameter("interrupt_id")],
            )
        },
        "/v1/feedback": {
            "post": operation(
                "createFeedback",
                "Create run feedback",
                action="feedback.create",
                success="201",
                request_schema="FeedbackRequest",
                response_schema="Feedback",
            )
        },
    }
    if store_enabled:
        paths.update(
            {
                "/v1/store/items": {
                    "post": operation(
                        "putStoreItem",
                        "Write a governed memory item",
                        action="memory.put",
                        request_schema="MemoryRequest",
                    ),
                    "delete": operation(
                        "deleteStoreItem",
                        "Delete a governed memory item",
                        action="memory.delete",
                        request_schema="MemoryRequest",
                    ),
                },
                "/v1/store/search": {
                    "post": operation(
                        "searchStore",
                        "Search governed memory",
                        action="memory.search",
                        request_schema="MemoryRequest",
                    )
                },
            }
        )
    identifier = {"type": "string", "format": "uuid"}
    schemas: dict[str, object] = {
        "Health": {
            "type": "object",
            "required": ["status"],
            "properties": {"status": {"type": "string"}},
        },
        "Info": {"type": "object", "additionalProperties": True},
        "ErrorResponse": {
            "type": "object",
            "required": ["error"],
            "properties": {
                "error": {
                    "type": "object",
                    "required": ["code", "message"],
                    "properties": {
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                    },
                }
            },
        },
        "Assistant": {
            "type": "object",
            "required": ["id", "template_id", "revision_id", "kind"],
            "properties": {
                "id": {"type": "string"},
                "template_id": {"type": "string"},
                "revision_id": identifier,
                "kind": {"type": "string", "enum": ["template", "alias"]},
            },
        },
        "Session": {
            "type": "object",
            "required": ["id", "tenant_id", "created_at"],
            "properties": {
                "id": identifier,
                "tenant_id": {"type": "string"},
                "created_at": {"type": "string", "format": "date-time"},
                "runs": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/Run"},
                },
            },
        },
        "Run": {
            "type": "object",
            "required": [
                "id",
                "plan_id",
                "revision_id",
                "session_id",
                "status",
                "version",
            ],
            "properties": {
                "id": identifier,
                "plan_id": identifier,
                "revision_id": identifier,
                "session_id": identifier,
                "status": {
                    "type": "string",
                    "enum": [item.value for item in RunStatus],
                },
                "state": {"type": "object"},
                "next_nodes": {"type": "array", "items": {"type": "string"}},
                "version": {"type": "integer", "minimum": 0},
            },
        },
        "Feedback": {"type": "object", "additionalProperties": True},
        "ItemPage": {
            "type": "object",
            "required": ["items", "next"],
            "properties": {
                "items": {"type": "array", "items": {}},
                "next": {"type": ["string", "null"]},
            },
        },
        "CreateAssistantRequest": {
            "type": "object",
            "required": ["id", "template_id"],
            "properties": {
                "id": {"type": "string"},
                "template_id": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "CreateRunRequest": {
            "type": "object",
            "required": ["assistant_id", "session_id"],
            "properties": {
                "assistant_id": {"type": "string"},
                "session_id": identifier,
                "state": {"type": "object"},
                "priority": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        "CreateSessionRunRequest": {
            "type": "object",
            "required": ["assistant_id"],
            "properties": {
                "assistant_id": {"type": "string"},
                "state": {"type": "object"},
                "priority": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        "ResumeRunRequest": {
            "type": "object",
            "required": ["confirm"],
            "properties": {"confirm": {"const": True}},
            "additionalProperties": False,
        },
        "InterruptDecisionRequest": {
            "type": "object",
            "required": ["kind", "reason"],
            "properties": {
                "kind": {"type": "string", "enum": ["approve", "edit", "reject"]},
                "reason": {"type": "string"},
                "payload": {"type": "object"},
            },
            "additionalProperties": False,
        },
        "FeedbackRequest": {
            "type": "object",
            "required": ["run_id", "key"],
            "properties": {
                "run_id": identifier,
                "key": {"type": "string"},
                "score": {"type": ["number", "null"], "minimum": -1, "maximum": 1},
                "value": {"type": ["string", "null"]},
            },
            "additionalProperties": False,
        },
        "MemoryRequest": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "user_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "session_id": {"type": "string"},
                "payload": {"type": "object"},
            },
            "additionalProperties": False,
        },
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "OpenRath Agent Server",
            "version": package_version,
            "description": "Beta v2 durable Agent Server API.",
        },
        "paths": paths,
        "components": {
            "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}},
            "schemas": schemas,
        },
    }


class AgentServer:
    def __init__(
        self,
        store: RunStore,
        runtime: LocalRuntime,
        *,
        auth: AuthProvider,
        resources: ResourceStore | None = None,
        embedded_worker: bool = False,
        worker_id: str = "agent-server",
        signals: SignalBus | None = None,
        worker_lease_seconds: float = 30.0,
        max_queued_runs_per_tenant: int = 1000,
        memory_executor: MemoryExecutor | None = None,
        memory_handler: MemoryHandler | None = None,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self.store = store
        self.runtime = runtime
        # Agent Server is the durable service profile. It must reject timeout
        # declarations that cannot be enforced before an assistant is exposed.
        self.runtime.production_mode = True
        self.auth = auth
        self.assistants: dict[str, _Assistant] = {}
        self.resources = resources or default_resource_store(store)
        self.embedded_worker = embedded_worker
        self.worker_id = worker_id
        self.signals = signals
        if worker_lease_seconds <= 0:
            raise ValueError("worker_lease_seconds must be positive")
        self.worker_lease_seconds = worker_lease_seconds
        if max_queued_runs_per_tenant < 1:
            raise ValueError("max_queued_runs_per_tenant must be positive")
        self.max_queued_runs_per_tenant = max_queued_runs_per_tenant
        if (memory_executor is None) != (memory_handler is None):
            raise ValueError(
                "memory_executor and memory_handler must be configured together"
            )
        self.memory_executor = memory_executor
        self.memory_handler = memory_handler
        self.audit_sink = audit_sink
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
    try:
        package_version = version("openrath")
    except PackageNotFoundError:
        package_version = "0+unknown"

    def error_response(code: str, message: str, status: int) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": code, "message": message}}, status_code=status
        )

    async def audit_action(
        request: Request,
        context: SecurityContext,
        *,
        kind: AuditKind,
        action: str,
        resource_kind: str,
        resource_id: str,
    ) -> None:
        if server.audit_sink is None:
            return
        request_id = UUID(str(request.state.request_id))
        await server.audit_sink.emit(
            AuditEvent(
                id=uuid4(),
                kind=kind,
                occurred_at=datetime.now(timezone.utc),
                tenant_id=context.tenant_id,
                principal_id=context.principal.id,
                request_id=request_id,
                trace_id=request_id.hex,
                action=action,
                resource_kind=resource_kind,
                resource_id=resource_id,
                outcome="allowed",
                reason="endpoint action grant and object scope validated",
                attributes={
                    "project_id": context.project_id,
                },
            )
        )

    async def json_body(request: Request) -> dict[str, object]:
        maximum = 1024 * 1024
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > maximum:
            raise ValueError("request body exceeds 1 MiB")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > maximum:
                raise ValueError("request body exceeds 1 MiB")
        value = json.loads(body or b"{}")
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    async def authenticate(
        request: Request,
        action: str | None = None,
    ) -> tuple[SecurityContext | None, JSONResponse | None]:
        context = await server.auth.authenticate(request.headers.get("authorization"))
        if context is None:
            return None, JSONResponse(
                {
                    "error": {
                        "code": "security.unauthenticated",
                        "message": "unauthenticated",
                    }
                },
                status_code=401,
            )
        if action is not None and not allows(context, action):
            return None, JSONResponse(
                {
                    "error": {
                        "code": "security.forbidden",
                        "message": f"missing grant: {action}",
                    }
                },
                status_code=403,
            )
        return context, None

    def run_visible(context: SecurityContext, run: Run) -> bool:
        if run.tenant_id != context.tenant_id:
            return False
        run_context = thaw_json(run.context)
        return not isinstance(run_context, Mapping) or project_allows(
            context,
            run_context.get("project_id"),
        )

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
                "version": package_version,
                "capabilities": [
                    "assistants",
                    "sessions",
                    "runs",
                    "events",
                    "sse",
                    "interrupts",
                    "feedback",
                ]
                + (["store"] if server.memory_handler is not None else []),
            }
        )

    async def openapi(request: Request) -> Response:
        return JSONResponse(
            _openapi_document(
                package_version,
                store_enabled=server.memory_handler is not None,
            )
        )

        secured: list[dict[str, list[object]]] = [{"bearerAuth": []}]

        def operation(
            operation_id: str,
            summary: str,
            *,
            success: str = "200",
            media_type: str = "application/json",
        ) -> dict[str, object]:
            return {
                "operationId": operation_id,
                "summary": summary,
                "security": secured,
                "responses": {
                    success: {
                        "description": "Success",
                        "content": {media_type: {"schema": {"type": "object"}}},
                    },
                    "400": {"description": "Invalid request"},
                    "401": {"description": "Unauthenticated"},
                    "403": {"description": "Forbidden"},
                    "404": {"description": "Not found"},
                    "409": {"description": "Conflict"},
                },
            }

        return JSONResponse(
            {
                "openapi": "3.1.0",
                "info": {
                    "title": "OpenRath Agent Server",
                    "version": package_version,
                },
                "paths": {
                    "/v1/assistants": {
                        "get": operation(
                            "listAssistants",
                            "List deployment templates and tenant aliases",
                        ),
                        "post": operation(
                            "createAssistantAlias",
                            "Create a tenant assistant alias",
                            success="201",
                        ),
                    },
                    "/v1/assistants/{assistant_id}": {
                        "get": operation(
                            "getAssistant",
                            "Get an assistant template or alias",
                        )
                    },
                    "/v1/sessions": {
                        "post": operation(
                            "createSession",
                            "Create a durable session",
                            success="201",
                        )
                    },
                    "/v1/sessions/{session_id}": {
                        "get": operation("getSession", "Get a durable session")
                    },
                    "/v1/sessions/{session_id}/runs": {
                        "post": operation(
                            "createSessionRun",
                            "Create a run in an existing session",
                            success="201",
                        )
                    },
                    "/v1/runs": {
                        "get": operation("listRuns", "List runs by cursor"),
                        "post": operation(
                            "createRun",
                            "Create a durable run",
                            success="201",
                        ),
                    },
                    "/v1/runs/{run_id}": {
                        "get": operation("getRun", "Get a durable run")
                    },
                    "/v1/runs/{run_id}/cancel": {
                        "post": operation("cancelRun", "Cancel a run")
                    },
                    "/v1/runs/{run_id}/resume": {
                        "post": operation(
                            "resumeRun",
                            "Resume a run requiring operator review",
                        )
                    },
                    "/v1/runs/{run_id}/events": {
                        "get": operation(
                            "listRunEvents",
                            "Replay ordered durable run events",
                        )
                    },
                    "/v1/runs/{run_id}/stream": {
                        "get": operation(
                            "streamRunEvents",
                            "Stream ordered run events with cursor resume",
                            media_type="text/event-stream",
                        )
                    },
                    "/v1/interrupts/{interrupt_id}/decision": {
                        "post": operation(
                            "decideInterrupt",
                            "Submit a durable interrupt decision",
                        )
                    },
                    "/v1/interrupts": {
                        "get": operation(
                            "listInterrupts",
                            "List pending durable interrupts",
                        )
                    },
                    "/v1/feedback": {
                        "post": operation(
                            "createFeedback",
                            "Create run feedback",
                            success="201",
                        )
                    },
                    "/v1/store/items": {
                        "post": operation(
                            "putStoreItem",
                            "Write a governed memory item",
                        ),
                        "delete": operation(
                            "deleteStoreItem",
                            "Delete a governed memory item",
                        ),
                    },
                    "/v1/store/search": {
                        "post": operation(
                            "searchStore",
                            "Search governed memory",
                        )
                    },
                },
                "components": {
                    "securitySchemes": {
                        "bearerAuth": {
                            "type": "http",
                            "scheme": "bearer",
                        }
                    }
                },
            }
        )

    async def metrics(request: Request) -> Response:
        context, error = await authenticate(request, "metrics.read")
        if error:
            return error
        assert context is not None
        queued, running = await asyncio.gather(
            asyncio.to_thread(server.store.count_runs, status=RunStatus.QUEUED),
            asyncio.to_thread(server.store.count_runs, status=RunStatus.RUNNING),
        )
        body = (
            "# TYPE openrath_runs gauge\n"
            f'openrath_runs{{status="queued"}} {queued}\n'
            f'openrath_runs{{status="running"}} {running}\n'
        )
        return Response(body, media_type="text/plain; version=0.0.4")

    async def list_assistants(request: Request) -> Response:
        context, error = await authenticate(request, "assistant.read")
        if error:
            return error
        assert context is not None
        templates = [
            {
                "id": item.id,
                "template_id": item.id,
                "revision_id": str(item.revision_id),
                "kind": "template",
            }
            for item in server.assistants.values()
        ]
        aliases = [
            {
                "id": item.id,
                "template_id": item.template_id,
                "revision_id": str(item.revision_id),
                "kind": "alias",
            }
            for item in server.resources.list_assistants(context.tenant_id)
        ]
        return JSONResponse({"items": templates + aliases})

    async def create_assistant(request: Request) -> Response:
        context, auth_error = await authenticate(request, "assistant.create")
        if auth_error:
            return auth_error
        assert context is not None
        try:
            body = await json_body(request)
            assistant_id = str(body["id"]).strip()
            template_id = str(body["template_id"]).strip()
            if not assistant_id or not template_id:
                raise ValueError("id and template_id are required")
            if assistant_id in server.assistants:
                raise ValueError("assistant id is reserved by a deployment template")
            template = server.assistants[template_id]
            await audit_action(
                request,
                context,
                kind=AuditKind.RUN_CONTROL,
                action="assistant.create",
                resource_kind="assistant",
                resource_id=assistant_id,
            )
            item = server.resources.create_assistant(
                tenant_id=context.tenant_id,
                id=assistant_id,
                template_id=template_id,
                revision_id=template.revision_id,
            )
            return JSONResponse(
                {
                    "id": item.id,
                    "template_id": item.template_id,
                    "revision_id": str(item.revision_id),
                    "kind": "alias",
                    "created_at": item.created_at.isoformat(),
                },
                status_code=201,
            )
        except KeyError as exc:
            return error_response(
                "request.invalid_argument",
                f"unknown deployment template: {exc}",
                400,
            )
        except (ValueError, TypeError) as exc:
            return error_response("request.invalid_argument", str(exc), 400)

    async def get_assistant(request: Request) -> Response:
        context, auth_error = await authenticate(request, "assistant.read")
        if auth_error:
            return auth_error
        assert context is not None
        assistant_id = request.path_params["assistant_id"]
        try:
            item = server.assistants[assistant_id]
            return JSONResponse(
                {
                    "id": item.id,
                    "template_id": item.id,
                    "revision_id": str(item.revision_id),
                    "kind": "template",
                }
            )
        except KeyError:
            try:
                alias = server.resources.get_assistant(context.tenant_id, assistant_id)
            except KeyError:
                return error_response("resource.not_found", "assistant not found", 404)
            return JSONResponse(
                {
                    "id": alias.id,
                    "template_id": alias.template_id,
                    "revision_id": str(alias.revision_id),
                    "kind": "alias",
                    "created_at": alias.created_at.isoformat(),
                }
            )

    async def create_session(request: Request) -> Response:
        context, auth_error = await authenticate(request, "session.create")
        if auth_error:
            return auth_error
        assert context is not None
        session = server.resources.create_session(context.tenant_id)
        return JSONResponse(
            {
                "id": str(session.id),
                "tenant_id": session.tenant_id,
                "created_at": session.created_at.isoformat(),
            },
            status_code=201,
        )

    async def get_session(request: Request) -> Response:
        context, auth_error = await authenticate(request, "session.read")
        if auth_error:
            return auth_error
        assert context is not None
        try:
            session = server.resources.get_session(
                UUID(request.path_params["session_id"])
            )
            if session.tenant_id != context.tenant_id:
                raise KeyError
        except (KeyError, ValueError):
            return error_response("resource.not_found", "session not found", 404)
        runs = [
            _run_json(run)
            for run in server.store.list_runs(
                tenant_id=context.tenant_id,
                session_id=session.id,
                limit=201,
            )
        ]
        return JSONResponse(
            {
                "id": str(session.id),
                "tenant_id": session.tenant_id,
                "created_at": session.created_at.isoformat(),
                "runs": runs,
            }
        )

    async def create_run(request: Request) -> Response:
        context, error = await authenticate(request, "run.create")
        if error:
            return error
        assert context is not None
        try:
            body = await json_body(request)
            assistant_id = str(body["assistant_id"])
            assistant = server.assistants.get(assistant_id)
            if assistant is None:
                alias = server.resources.get_assistant(context.tenant_id, assistant_id)
                assistant = server.assistants.get(alias.template_id)
                if assistant is None or assistant.revision_id != alias.revision_id:
                    raise ValueError("assistant deployment revision is unavailable")
            session_id = UUID(str(body["session_id"]))
            try:
                known_session = server.resources.get_session(session_id)
            except KeyError:
                raise KeyError("session_id") from None
            if known_session.tenant_id != context.tenant_id:
                raise KeyError("session_id")
            run_context = RunContext(
                security=context,
                revision_id=assistant.revision_id,
            )
            state = body.get("state") or {}
            if not isinstance(state, Mapping):
                raise ValueError("state must be a JSON object")
            queued = len(
                server.store.list_runs(
                    tenant_id=context.tenant_id,
                    statuses=(RunStatus.QUEUED,),
                    limit=server.max_queued_runs_per_tenant,
                )
            )
            if queued >= server.max_queued_runs_per_tenant:
                return error_response(
                    "resource.exhausted",
                    "tenant run queue is at capacity",
                    429,
                )
            run = server.runtime.submit(
                assistant.workflow,
                session_id=session_id,
                context=run_context,
                state=cast(Mapping[str, object], state),
                idempotency_key=request.headers.get("idempotency-key"),
                priority=int(str(body.get("priority", 0))),
            )
            if server.signals is not None:
                server.signals.publish(
                    RunSignal(
                        kind=SignalKind.WAKE,
                        run_id=run.id,
                        tenant_id=run.tenant_id,
                        created_at=run.updated_at,
                    )
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

    async def create_session_run(request: Request) -> Response:
        try:
            session_id = UUID(request.path_params["session_id"])
            body = await json_body(request)
        except (ValueError, TypeError):
            return error_response(
                "request.invalid_argument", "invalid session or body", 400
            )
        body["session_id"] = str(session_id)
        request._body = json.dumps(body).encode()  # noqa: SLF001
        return await create_run(request)

    async def list_runs(request: Request) -> Response:
        context, auth_error = await authenticate(request, "run.read")
        if auth_error:
            return auth_error
        assert context is not None
        try:
            limit = min(max(int(request.query_params.get("limit", "50")), 1), 200)
            after = request.query_params.get("after")
            after_id = UUID(after) if after else None
        except ValueError:
            return error_response(
                "request.invalid_argument", "invalid pagination cursor", 400
            )
        try:
            values = await asyncio.to_thread(
                server.store.list_runs,
                tenant_id=context.tenant_id,
                after=after_id,
                limit=limit + 1,
            )
        except KeyError:
            return error_response(
                "request.invalid_argument", "unknown pagination cursor", 400
            )
        page = values[:limit]
        next_cursor = str(page[-1].id) if len(values) > limit else None
        return JSONResponse(
            {"items": [_run_json(item) for item in page], "next": next_cursor}
        )

    async def get_run(request: Request) -> Response:
        context, error = await authenticate(request, "run.read")
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
        if not run_visible(context, run):
            return JSONResponse(
                {"error": {"code": "resource.not_found", "message": "run not found"}},
                status_code=404,
            )
        return JSONResponse(_run_json(run))

    async def cancel_run(request: Request) -> Response:
        context, error = await authenticate(request, "run.cancel")
        if error:
            return error
        assert context is not None
        try:
            run = server.store.get_run(UUID(request.path_params["run_id"]))
            if not run_visible(context, run):
                raise KeyError
            await audit_action(
                request,
                context,
                kind=AuditKind.RUN_CONTROL,
                action="run.cancel",
                resource_kind="run",
                resource_id=str(run.id),
            )
            cancelled = server.store.transition_run(
                run.id,
                expected_version=run.version,
                target=RunStatus.CANCELLED,
            )
            if server.signals is not None:
                server.signals.publish(
                    RunSignal(
                        kind=SignalKind.CANCEL,
                        run_id=run.id,
                        tenant_id=run.tenant_id,
                        created_at=cancelled.updated_at,
                    )
                )
            return JSONResponse(_run_json(cancelled))
        except (KeyError, ValueError):
            return JSONResponse(
                {"error": {"code": "resource.not_found", "message": "run not found"}},
                status_code=404,
            )
        except RathError as exc:
            return JSONResponse({"error": exc.to_dict()}, status_code=409)

    async def resume_run(request: Request) -> Response:
        context, auth_error = await authenticate(request, "run.resume")
        if auth_error:
            return auth_error
        assert context is not None
        try:
            run = server.store.get_run(UUID(request.path_params["run_id"]))
            if not run_visible(context, run):
                raise KeyError
            body = await json_body(request)
            if (
                run.status is not RunStatus.NEEDS_REVIEW
                or body.get("confirm") is not True
            ):
                return error_response(
                    "request.invalid_argument",
                    "resume requires NEEDS_REVIEW status and confirm=true",
                    400,
                )
            await audit_action(
                request,
                context,
                kind=AuditKind.OPERATOR_OVERRIDE,
                action="run.resume",
                resource_kind="run",
                resource_id=str(run.id),
            )
            resumed = server.store.transition_run(
                run.id,
                expected_version=run.version,
                target=RunStatus.QUEUED,
            )
            return JSONResponse(_run_json(resumed))
        except (KeyError, ValueError):
            return error_response("resource.not_found", "run not found", 404)
        except RathError as exc:
            return JSONResponse({"error": exc.to_dict()}, status_code=409)

    async def events(request: Request) -> Response:
        context, error = await authenticate(request, "run.read")
        if error:
            return error
        assert context is not None
        try:
            run_id = UUID(request.path_params["run_id"])
            run = server.store.get_run(run_id)
            if not run_visible(context, run):
                raise KeyError
        except (KeyError, ValueError):
            return JSONResponse(
                {"error": {"code": "resource.not_found", "message": "run not found"}},
                status_code=404,
            )
        try:
            cursor_value = request.query_params.get("after")
            if cursor_value is None:
                cursor_value = request.headers.get("last-event-id", "0")
            after = int(cursor_value)
            if after < 0:
                raise ValueError
            limit = min(max(int(request.query_params.get("limit", "200")), 1), 1000)
        except ValueError:
            return error_response(
                "request.invalid_argument", "invalid event cursor", 400
            )
        items = [
            {
                "id": str(event.sequence),
                "run_id": str(event.run_id),
                "sequence": event.sequence,
                "type": event.type,
                "time": event.created_at.isoformat(),
                "data": thaw_json(event.data),
            }
            for event in await asyncio.to_thread(
                server.store.list_run_events,
                run_id,
                after_sequence=after,
                limit=limit,
            )
        ]
        return JSONResponse(
            {
                "items": items,
                "next": str(items[-1]["sequence"]) if len(items) == limit else None,
            }
        )

    async def stream(request: Request) -> Response:
        last_event = request.headers.get("last-event-id")
        response = await events(request)
        if response.status_code != 200:
            return response
        payload = json.loads(bytes(response.body))
        follow = request.query_params.get("follow", "false").lower() == "true"
        run_id = UUID(request.path_params["run_id"])

        async def generate() -> AsyncIterator[str]:
            cursor = int(last_event or request.query_params.get("after", "0"))
            initial = payload["items"]
            idle_delay = 0.1
            while True:
                emitted = False
                durable_events = (
                    ()
                    if initial
                    else await asyncio.to_thread(
                        server.store.list_run_events,
                        run_id,
                        after_sequence=cursor,
                        limit=200,
                    )
                )
                items = initial or [
                    {
                        "sequence": event.sequence,
                        "type": event.type,
                        "run_id": str(event.run_id),
                        "time": event.created_at.isoformat(),
                        "data": thaw_json(event.data),
                    }
                    for event in durable_events
                ]
                initial = []
                for item in items:
                    emitted = True
                    idle_delay = 0.1
                    cursor = int(item["sequence"])
                    yield (
                        f"id: {cursor}\nevent: {item['type']}\n"
                        f"data: {json.dumps(item, separators=(',', ':'))}\n\n"
                    )
                if not follow:
                    break
                if await request.is_disconnected():
                    break
                run = await asyncio.to_thread(server.store.get_run, run_id)
                if (
                    run.status
                    in {
                        RunStatus.SUCCEEDED,
                        RunStatus.FAILED,
                        RunStatus.CANCELLED,
                        RunStatus.TIMED_OUT,
                    }
                    and not emitted
                ):
                    break
                if not emitted:
                    yield ": keep-alive\n\n"
                    idle_delay = min(idle_delay * 2, 2.0)
                await asyncio.sleep(idle_delay)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    async def decide_interrupt(request: Request) -> Response:
        context, auth_error = await authenticate(request, "interrupt.decide")
        if auth_error:
            return auth_error
        assert context is not None
        try:
            interrupt_id = UUID(request.path_params["interrupt_id"])
            interrupt = server.store.get_interrupt(interrupt_id)
            run = server.store.get_run(interrupt.run_id)
            if not run_visible(context, run):
                raise KeyError
            body = await json_body(request)
            payload = body.get("payload") or {}
            if not isinstance(payload, Mapping):
                raise ValueError("decision payload must be a JSON object")
            decision = ApprovalDecision(
                kind=ApprovalDecisionKind(str(body["kind"])),
                actor_id=context.principal.id,
                reason=str(body["reason"]),
                payload=cast(Mapping[str, JSONValue], payload),
            )
            await audit_action(
                request,
                context,
                kind=AuditKind.OPERATOR_OVERRIDE,
                action="interrupt.decide",
                resource_kind="interrupt",
                resource_id=str(interrupt_id),
            )
            updated = server.store.decide_interrupt(
                interrupt_id,
                decision=decision,
                expected_run_version=run.version,
            )
            return JSONResponse(_run_json(updated))
        except (KeyError, ValueError, TypeError) as exc:
            return error_response("request.invalid_argument", str(exc), 400)
        except RathError as exc:
            return JSONResponse({"error": exc.to_dict()}, status_code=409)

    async def list_interrupts(request: Request) -> Response:
        context, auth_error = await authenticate(request, "interrupt.read")
        if auth_error:
            return auth_error
        assert context is not None
        try:
            limit = min(max(int(request.query_params.get("limit", "50")), 1), 200)
            pending_only = (
                request.query_params.get("pending", "true").lower() != "false"
            )
        except ValueError:
            return error_response(
                "request.invalid_argument", "invalid pagination limit", 400
            )
        values = server.store.list_interrupts(
            tenant_id=context.tenant_id,
            pending_only=pending_only,
        )
        return JSONResponse(
            {
                "items": [_interrupt_json(item) for item in values[:limit]],
                "next": (str(values[limit - 1].id) if len(values) > limit else None),
            }
        )

    async def create_feedback(request: Request) -> Response:
        context, auth_error = await authenticate(request, "feedback.create")
        if auth_error:
            return auth_error
        assert context is not None
        try:
            body = await json_body(request)
            run = server.store.get_run(UUID(str(body["run_id"])))
            if not run_visible(context, run):
                raise KeyError
            score = body.get("score")
            numeric_score = float(str(score)) if score is not None else None
            if numeric_score is not None and not -1 <= numeric_score <= 1:
                raise ValueError("score must be between -1 and 1")
            key = str(body["key"])
            if not key:
                raise ValueError("feedback key is required")
            feedback = server.resources.create_feedback(
                tenant_id=context.tenant_id,
                run_id=run.id,
                key=key,
                score=numeric_score,
                value=str(body["value"]) if body.get("value") is not None else None,
            )
            return JSONResponse(
                {
                    "id": str(feedback.id),
                    "run_id": str(feedback.run_id),
                    "key": feedback.key,
                    "score": feedback.score,
                    "value": feedback.value,
                    "created_at": feedback.created_at.isoformat(),
                },
                status_code=201,
            )
        except (KeyError, ValueError, TypeError) as exc:
            return error_response("request.invalid_argument", str(exc), 400)

    async def execute_store_operation(
        request: Request,
        operation: str,
    ) -> Response:
        context, auth_error = await authenticate(request, f"memory.{operation}")
        if auth_error:
            return auth_error
        assert context is not None
        if server.memory_executor is None or server.memory_handler is None:
            return error_response(
                "runtime.unavailable",
                "store capability is not configured",
                501,
            )
        try:
            body = await json_body(request)
            requested_tenant = body.get("tenant_id")
            if (
                requested_tenant is not None
                and str(requested_tenant) != context.tenant_id
            ):
                raise PermissionError("memory namespace tenant mismatch")
            requested_user = (
                str(body["user_id"]) if body.get("user_id") is not None else None
            )
            if (
                requested_user is not None
                and requested_user != context.principal.id
                and not allows(context, "memory.admin")
            ):
                raise PermissionError("memory namespace owner mismatch")
            namespace = MemoryNamespace(
                tenant_id=context.tenant_id,
                user_id=requested_user,
                agent_id=(
                    str(body["agent_id"]) if body.get("agent_id") is not None else None
                ),
                session_id=(
                    str(body["session_id"])
                    if body.get("session_id") is not None
                    else None
                ),
                # HTTP input never upgrades memory trust.
                trust=TrustLevel.UNTRUSTED,
            )
            payload = body.get("payload", {})
            if not isinstance(payload, Mapping):
                raise ValueError("payload must be a JSON object")
            run_context = RunContext(
                security=context,
                revision_id=UUID(int=0),
            )
            adapter_context = AdapterRequestContext(
                run_id=uuid4(),
                node_id=f"store.{operation}",
                tenant_id=context.tenant_id,
                deadline=None,
                trace_context=run_context.trace_context,
                idempotency_key=request.headers.get("idempotency-key"),
                policy_constraints=PolicyConstraints(),
            )
            await audit_action(
                request,
                context,
                kind=AuditKind.MEMORY_ACCESS,
                action=f"memory.{operation}",
                resource_kind="memory_namespace",
                resource_id=":".join(
                    item
                    for item in (
                        namespace.tenant_id,
                        namespace.user_id,
                        namespace.agent_id,
                        namespace.session_id,
                    )
                    if item is not None
                ),
            )
            result = await server.memory_executor.execute(
                server.memory_handler,
                cast(Any, operation),
                namespace,
                cast(Mapping[str, object], payload),
                adapter_context=adapter_context,
                run_context=run_context,
            )
            return JSONResponse({"result": result})
        except PermissionError as exc:
            return error_response("security.forbidden", str(exc), 403)
        except (KeyError, ValueError, TypeError) as exc:
            return error_response("request.invalid_argument", str(exc), 400)
        except RathError as exc:
            status = (
                403
                if exc.code
                in {
                    ErrorCode.FORBIDDEN,
                    ErrorCode.APPROVAL_REQUIRED,
                    ErrorCode.POLICY_ERROR,
                }
                else 409
            )
            return JSONResponse({"error": exc.to_dict()}, status_code=status)

    async def put_store_item(request: Request) -> Response:
        return await execute_store_operation(request, "put")

    async def search_store(request: Request) -> Response:
        return await execute_store_operation(request, "search")

    async def delete_store_item(request: Request) -> Response:
        return await execute_store_operation(request, "delete")

    async def worker_loop() -> None:
        while True:
            await asyncio.to_thread(server.store.expire_interrupts)
            await asyncio.to_thread(server.runtime.reconcile_effects)
            await asyncio.to_thread(server.store.requeue_expired_leases)
            result = await asyncio.to_thread(
                server.runtime.work_once,
                worker_id=server.worker_id,
                lease_seconds=server.worker_lease_seconds,
            )
            if result is not None:
                await asyncio.sleep(0)
            elif server.signals is not None:
                await asyncio.to_thread(
                    server.signals.receive,
                    timeout_seconds=0.1,
                )
            else:
                await asyncio.sleep(0.1)

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        task = (
            asyncio.create_task(worker_loop(), name="openrath-embedded-worker")
            if server.embedded_worker
            else None
        )
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    app = Starlette(
        routes=[
            Route("/health/live", live),
            Route("/health/ready", ready),
            Route("/info", info),
            Route("/openapi.json", openapi),
            Route("/metrics", metrics),
            Route("/v1/assistants", list_assistants, methods=["GET"]),
            Route("/v1/assistants", create_assistant, methods=["POST"]),
            Route("/v1/assistants/{assistant_id}", get_assistant),
            Route("/v1/sessions", create_session, methods=["POST"]),
            Route("/v1/sessions/{session_id}", get_session),
            Route(
                "/v1/sessions/{session_id}/runs",
                create_session_run,
                methods=["POST"],
            ),
            Route("/v1/runs", create_run, methods=["POST"]),
            Route("/v1/runs", list_runs, methods=["GET"]),
            Route("/v1/runs/{run_id}", get_run),
            Route("/v1/runs/{run_id}/cancel", cancel_run, methods=["POST"]),
            Route("/v1/runs/{run_id}/resume", resume_run, methods=["POST"]),
            Route("/v1/runs/{run_id}/events", events),
            Route("/v1/runs/{run_id}/stream", stream),
            Route("/v1/interrupts", list_interrupts, methods=["GET"]),
            Route(
                "/v1/interrupts/{interrupt_id}/decision",
                decide_interrupt,
                methods=["POST"],
            ),
            Route("/v1/feedback", create_feedback, methods=["POST"]),
            Route("/v1/store/items", put_store_item, methods=["POST"]),
            Route("/v1/store/items", delete_store_item, methods=["DELETE"]),
            Route("/v1/store/search", search_store, methods=["POST"]),
        ],
        lifespan=lifespan,
    )

    app.add_middleware(_SecurityHeadersMiddleware)

    return app
