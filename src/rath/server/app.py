"""Starlette Agent Server exposing durable Run resources and SSE replay."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
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
from rath.security import PolicyConstraints, SecurityContext, TrustLevel
from rath.server.auth import AuthProvider
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
            value.expires_at.isoformat()
            if value.expires_at is not None
            else None
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
            value.decided_at.isoformat()
            if value.decided_at is not None
            else None
        ),
    }


@dataclass(frozen=True, slots=True)
class _Assistant:
    id: str
    workflow: object
    revision_id: UUID


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
    ) -> None:
        self.store = store
        self.runtime = runtime
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
            {
                "openapi": "3.1.0",
                "info": {
                    "title": "OpenRath Agent Server",
                    "version": package_version,
                },
                "paths": {
                    "/v1/assistants": {},
                    "/v1/sessions": {},
                    "/v1/runs": {},
                    "/v1/runs/{run_id}/events": {},
                    "/v1/runs/{run_id}/stream": {},
                    "/v1/interrupts/{interrupt_id}/decision": {},
                    "/v1/interrupts": {},
                    "/v1/feedback": {},
                    "/v1/store/items": {},
                    "/v1/store/search": {},
                },
            }
        )

    async def metrics(request: Request) -> Response:
        queued = running = 0
        for tenant_id in server.resources.count_tenants():
            for run in server.store.list_runs(tenant_id=tenant_id):
                queued += int(run.status is RunStatus.QUEUED)
                running += int(run.status is RunStatus.RUNNING)
        body = (
            "# TYPE openrath_runs gauge\n"
            f'openrath_runs{{status="queued"}} {queued}\n'
            f'openrath_runs{{status="running"}} {running}\n'
        )
        return Response(body, media_type="text/plain; version=0.0.4")

    async def list_assistants(request: Request) -> Response:
        context, error = await authenticate(request)
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
        return JSONResponse(
            {"items": templates + aliases}
        )

    async def create_assistant(request: Request) -> Response:
        context, auth_error = await authenticate(request)
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
        context, auth_error = await authenticate(request)
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
                alias = server.resources.get_assistant(
                    context.tenant_id, assistant_id
                )
            except KeyError:
                return error_response(
                    "resource.not_found", "assistant not found", 404
                )
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
        context, auth_error = await authenticate(request)
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
        context, auth_error = await authenticate(request)
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
            for run in server.store.list_runs(tenant_id=context.tenant_id)
            if run.session_id == session.id
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
        context, error = await authenticate(request)
        if error:
            return error
        assert context is not None
        try:
            body = await json_body(request)
            assistant_id = str(body["assistant_id"])
            assistant = server.assistants.get(assistant_id)
            if assistant is None:
                alias = server.resources.get_assistant(
                    context.tenant_id, assistant_id
                )
                assistant = server.assistants.get(alias.template_id)
                if assistant is None or assistant.revision_id != alias.revision_id:
                    raise ValueError(
                        "assistant deployment revision is unavailable"
                    )
            session_id = UUID(str(body["session_id"]))
            try:
                known_session = server.resources.get_session(session_id)
            except KeyError:
                known_session = None
            if (
                known_session is not None
                and known_session.tenant_id != context.tenant_id
            ):
                raise KeyError("session_id")
            run_context = RunContext(
                security=context,
                revision_id=assistant.revision_id,
            )
            state = body.get("state") or {}
            if not isinstance(state, Mapping):
                raise ValueError("state must be a JSON object")
            queued = sum(
                run.status is RunStatus.QUEUED
                for run in server.store.list_runs(tenant_id=context.tenant_id)
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
        context, auth_error = await authenticate(request)
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
        values = list(server.store.list_runs(tenant_id=context.tenant_id))
        if after_id is not None:
            try:
                offset = next(i for i, item in enumerate(values) if item.id == after_id) + 1
            except StopIteration:
                return error_response(
                    "request.invalid_argument", "unknown pagination cursor", 400
                )
            values = values[offset:]
        page = values[:limit]
        next_cursor = str(page[-1].id) if len(values) > limit else None
        return JSONResponse(
            {"items": [_run_json(item) for item in page], "next": next_cursor}
        )

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
        context, auth_error = await authenticate(request)
        if auth_error:
            return auth_error
        assert context is not None
        try:
            run = server.store.get_run(UUID(request.path_params["run_id"]))
            if run.tenant_id != context.tenant_id:
                raise KeyError
            body = await json_body(request)
            if run.status is not RunStatus.NEEDS_REVIEW or body.get("confirm") is not True:
                return error_response(
                    "request.invalid_argument",
                    "resume requires NEEDS_REVIEW status and confirm=true",
                    400,
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
        try:
            after = int(request.query_params.get("after", "0"))
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
            for event in server.store.list_run_events(run_id)
            if event.sequence > after
        ][:limit]
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
        if last_event and "after" not in request.query_params:
            payload["items"] = [
                item
                for item in payload["items"]
                if int(item["sequence"]) > int(last_event)
            ]
        follow = request.query_params.get("follow", "false").lower() == "true"
        run_id = UUID(request.path_params["run_id"])

        async def generate() -> AsyncIterator[str]:
            cursor = int(last_event or request.query_params.get("after", "0"))
            initial = payload["items"]
            while True:
                emitted = False
                items = initial or [
                    {
                        "sequence": event.sequence,
                        "type": event.type,
                        "run_id": str(event.run_id),
                        "time": event.created_at.isoformat(),
                        "data": thaw_json(event.data),
                    }
                    for event in server.store.list_run_events(run_id)
                    if event.sequence > cursor
                ]
                initial = []
                for item in items:
                    emitted = True
                    cursor = int(item["sequence"])
                    yield (
                        f"id: {cursor}\nevent: {item['type']}\n"
                        f"data: {json.dumps(item, separators=(',', ':'))}\n\n"
                    )
                if not follow:
                    break
                run = server.store.get_run(run_id)
                if run.status in {
                    RunStatus.SUCCEEDED,
                    RunStatus.FAILED,
                    RunStatus.CANCELLED,
                    RunStatus.TIMED_OUT,
                } and not emitted:
                    break
                if not emitted:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0.25)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    async def decide_interrupt(request: Request) -> Response:
        context, auth_error = await authenticate(request)
        if auth_error:
            return auth_error
        assert context is not None
        try:
            interrupt_id = UUID(request.path_params["interrupt_id"])
            interrupt = server.store.get_interrupt(interrupt_id)
            run = server.store.get_run(interrupt.run_id)
            if run.tenant_id != context.tenant_id:
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
        context, auth_error = await authenticate(request)
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
                "next": (
                    str(values[limit - 1].id) if len(values) > limit else None
                ),
            }
        )

    async def create_feedback(request: Request) -> Response:
        context, auth_error = await authenticate(request)
        if auth_error:
            return auth_error
        assert context is not None
        try:
            body = await json_body(request)
            run = server.store.get_run(UUID(str(body["run_id"])))
            if run.tenant_id != context.tenant_id:
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
        context, auth_error = await authenticate(request)
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
            namespace = MemoryNamespace(
                tenant_id=context.tenant_id,
                user_id=(
                    str(body["user_id"]) if body.get("user_id") is not None else None
                ),
                agent_id=(
                    str(body["agent_id"])
                    if body.get("agent_id") is not None
                    else None
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
            await asyncio.to_thread(server.store.requeue_expired_leases)
            result = await asyncio.to_thread(
                server.runtime.work_once,
                worker_id=server.worker_id,
                lease_seconds=server.worker_lease_seconds,
            )
            await asyncio.sleep(0 if result is not None else 0.1)

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
