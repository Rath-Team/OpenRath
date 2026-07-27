"""Embedded durable executor for explicit Workflow step boundaries."""

from __future__ import annotations

import inspect
import threading
import time
from asyncio import TimeoutError as AsyncTimeoutError
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Coroutine, cast
from uuid import UUID

from rath._json import JSONValue, thaw_json
from rath.context import DeadlineExceededError, RunContext, TraceContext
from rath.definition import ExecutionPlan, NodeKind, WorkflowCompiler
from rath.observability import (
    GuardedTelemetry,
    NoOpTelemetry,
    StructuredLogger,
    Telemetry,
)
from rath.runtime.models import (
    TERMINAL_RUN_STATUSES,
    ApprovalDecision,
    Checkpoint,
    ClaimedRun,
    ConflictError,
    Interrupt,
    InterruptKind,
    Run,
    RunStatus,
)
from rath.runtime.store import RunStore
from rath.security import Principal, PrincipalKind, SecurityContext

__all__ = ["LocalRuntime", "StepContext"]


@dataclass(frozen=True, slots=True)
class StepContext:
    run_id: UUID
    request: RunContext
    worker_id: str
    fencing_token: int
    _interrupt_handler: Callable[
        [InterruptKind, Mapping[str, object], float | None], ApprovalDecision
    ] = field(repr=False)

    def interrupt(
        self,
        kind: InterruptKind,
        request: Mapping[str, object],
        *,
        timeout_seconds: float | None = None,
    ) -> ApprovalDecision:
        """Suspend durably on first call and return the decision after resume."""
        return self._interrupt_handler(kind, request, timeout_seconds)


class _RunSuspended(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _Registration:
    workflow: object
    plan: ExecutionPlan


class LocalRuntime:
    """Sync façade over the durable local worker engine."""

    def __init__(
        self,
        store: RunStore,
        *,
        telemetry: Telemetry | None = None,
        structured_logger: StructuredLogger | None = None,
    ) -> None:
        self.store = store
        self.telemetry = GuardedTelemetry(telemetry or NoOpTelemetry())
        self.structured_logger = structured_logger or StructuredLogger()
        self._registrations: dict[UUID, _Registration] = {}
        self._contexts: dict[UUID, RunContext] = {}

    def register(self, workflow: object, *, revision_id: UUID) -> ExecutionPlan:
        plan = WorkflowCompiler().compile(workflow, revision_id=revision_id)
        if not plan.durable:
            raise ValueError(
                "durable runtime requires explicit @step boundaries; "
                f"issues: {plan.compatibility_issues}"
            )
        self._registrations[plan.id] = _Registration(workflow=workflow, plan=plan)
        return plan

    def submit(
        self,
        workflow: object,
        *,
        session_id: UUID,
        context: RunContext,
        state: Mapping[str, object] | None = None,
        idempotency_key: str | None = None,
        priority: int = 0,
    ) -> Run:
        context.ensure_active()
        plan = self.register(workflow, revision_id=context.revision_id)
        run = Run.create(
            plan_id=plan.id,
            revision_id=plan.revision_id,
            session_id=session_id,
            tenant_id=context.security.tenant_id,
            state=state,
            next_nodes=(plan.definition.entrypoint,),
            idempotency_key=idempotency_key,
            context={
                "principal": {
                    "id": context.security.principal.id,
                    "kind": context.security.principal.kind.value,
                    "claims": context.security.principal.claims,
                },
                "project_id": context.security.project_id,
                "grants": sorted(context.security.grants),
                "attributes": context.security.attributes,
                "request_id": str(context.request_id),
                "trace_id": context.trace_context.trace_id,
                "span_id": context.trace_context.span_id,
                "sampled": context.trace_context.sampled,
                "deadline": (
                    context.deadline.isoformat() if context.deadline is not None else None
                ),
            },
            priority=priority,
        )
        created = self.store.create_run(run)
        self._contexts[created.id] = context
        self.structured_logger.emit(
            "run.submitted",
            context=context.trace_context,
            fields={
                "run_id": str(created.id),
                "tenant_id": created.tenant_id,
                "plan_id": str(created.plan_id),
                "revision_id": str(created.revision_id),
                "status": created.status.value,
            },
        )
        return created

    def work_once(
        self,
        *,
        worker_id: str,
        lease_seconds: float = 30.0,
        max_steps: int | None = None,
        now: datetime | None = None,
    ) -> Run | None:
        claim = self.store.claim_next(
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            now=now,
        )
        if claim is None:
            return None
        claim_context = self._contexts.get(claim.run.id)
        self.structured_logger.emit(
            "run.claimed",
            context=(
                claim_context.trace_context if claim_context is not None else None
            ),
            fields={
                "run_id": str(claim.run.id),
                "tenant_id": claim.run.tenant_id,
                "worker_id": worker_id,
                "fencing_token": claim.lease.fencing_token,
            },
        )
        try:
            stop_heartbeat = threading.Event()
            heartbeat = threading.Thread(
                target=self._heartbeat,
                args=(claim, lease_seconds, stop_heartbeat),
                daemon=True,
                name=f"openrath-lease-{claim.run.id}",
            )
            heartbeat.start()
            try:
                result = self._execute_claim(claim, max_steps=max_steps)
                self._forget_context_if_terminal(result)
                return result
            finally:
                stop_heartbeat.set()
                heartbeat.join(timeout=min(1.0, lease_seconds))
        except _RunSuspended:
            waiting = self.store.get_run(claim.run.id)
            self.structured_logger.emit(
                "run.suspended",
                context=(
                    claim_context.trace_context
                    if claim_context is not None
                    else None
                ),
                fields={
                    "run_id": str(waiting.id),
                    "tenant_id": waiting.tenant_id,
                    "status": waiting.status.value,
                },
            )
            return waiting
        except BaseException as exc:
            current = self.store.get_run(claim.run.id)
            if current.status in TERMINAL_RUN_STATUSES:
                self._forget_context_if_terminal(current)
                return current
            target = (
                RunStatus.TIMED_OUT
                if isinstance(
                    exc,
                    (
                        AsyncTimeoutError,
                        DeadlineExceededError,
                        TimeoutError,
                        FutureTimeout,
                    ),
                )
                else RunStatus.FAILED
            )
            failed = self.store.finish_claim(
                claim.run.id,
                worker_id=worker_id,
                fencing_token=claim.lease.fencing_token,
                expected_run_version=current.version,
                target=target,
                event_type="run.execution.failed",
                event_data={
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
            )
            self.structured_logger.emit(
                "run.failed",
                context=(
                    claim_context.trace_context
                    if claim_context is not None
                    else None
                ),
                fields={
                    "run_id": str(failed.id),
                    "tenant_id": failed.tenant_id,
                    "status": failed.status.value,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            self._forget_context_if_terminal(failed)
            return failed

    def _execute_claim(
        self,
        claim: ClaimedRun,
        *,
        max_steps: int | None,
    ) -> Run:
        registration = self._registrations.get(claim.run.plan_id)
        if registration is None:
            raise RuntimeError(f"execution plan {claim.run.plan_id} is not registered")
        context = self._contexts.get(claim.run.id)
        if context is None:
            context = self._restore_context(claim.run)
        run = claim.run
        steps = 0
        by_id = {node.id: node for node in registration.plan.nodes}
        while run.next_nodes and (max_steps is None or steps < max_steps):
            context.ensure_active()
            durable = self.store.get_run(run.id)
            if durable.status in TERMINAL_RUN_STATUSES:
                return durable
            if durable.version != run.version:
                raise ConflictError("run changed while worker was executing")
            node_id = run.next_nodes[0]
            node = by_id[node_id]
            state_value = thaw_json(run.state)
            assert isinstance(state_value, dict)
            handler = getattr(registration.workflow, node.id)
            latest = self.store.latest_checkpoint(run.id)
            checkpoint_sequence = 1 if latest is None else latest.sequence + 1

            def request_interrupt(
                kind: InterruptKind,
                request: Mapping[str, object],
                timeout_seconds: float | None,
            ) -> ApprovalDecision:
                for existing in self.store.list_interrupts(
                    tenant_id=run.tenant_id,
                    pending_only=False,
                ):
                    if (
                        existing.run_id == run.id
                        and existing.request.get("_openrath_node_id") == node.id
                        and existing.request.get(
                            "_openrath_checkpoint_sequence"
                        )
                        == checkpoint_sequence
                    ):
                        if existing.decision is None:
                            raise _RunSuspended("run is waiting for a decision")
                        return existing.decision
                interrupt = Interrupt.create(
                    run_id=run.id,
                    kind=kind,
                    request={
                        **request,
                        "_openrath_node_id": node.id,
                        "_openrath_checkpoint_sequence": checkpoint_sequence,
                    },
                    timeout_seconds=timeout_seconds,
                )
                self.store.create_interrupt(
                    interrupt,
                    expected_run_version=run.version,
                )
                raise _RunSuspended("run was suspended for a decision")

            step_context = StepContext(
                run_id=run.id,
                request=context,
                worker_id=claim.lease.holder_worker_id,
                fencing_token=claim.lease.fencing_token,
                _interrupt_handler=request_interrupt,
            )
            with self.telemetry.span(
                "openrath.node",
                context=context.trace_context,
                attributes={"run_id": str(run.id), "node_id": node.id},
            ):
                result = self._invoke_with_retry(
                    handler,
                    state_value,
                    step_context,
                    node=node,
                    run=run,
                )

            next_nodes: tuple[str, ...]
            if node.kind is NodeKind.ROUTER:
                if not isinstance(result, str) or result not in node.successors:
                    raise ValueError(
                        f"router {node.id!r} returned invalid successor {result!r}"
                    )
                next_nodes = (result,)
                next_state = state_value
            else:
                if result is None:
                    next_state = state_value
                elif isinstance(result, Mapping):
                    next_state = dict(result)
                else:
                    raise TypeError(
                        f"step {node.id!r} must return a mapping or None"
                    )
                if len(node.successors) > 1:
                    raise ValueError(
                        f"step {node.id!r} has multiple successors; use @router"
                    )
                next_nodes = node.successors

            checkpoint = Checkpoint.create(
                run_id=run.id,
                sequence=checkpoint_sequence,
                plan_hash=registration.plan.definition_hash,
                state=next_state,
                next_nodes=next_nodes,
                effect_watermark=0,
            )
            run = self.store.commit_checkpoint(
                checkpoint,
                worker_id=claim.lease.holder_worker_id,
                fencing_token=claim.lease.fencing_token,
                expected_run_version=run.version,
            )
            steps += 1
            self.telemetry.increment(
                "openrath.node.completed",
                attributes={"kind": node.kind.value},
            )

        if not run.next_nodes:
            completed = self.store.finish_claim(
                run.id,
                worker_id=claim.lease.holder_worker_id,
                fencing_token=claim.lease.fencing_token,
                expected_run_version=run.version,
                target=RunStatus.SUCCEEDED,
            )
            self.structured_logger.emit(
                "run.completed",
                context=context.trace_context,
                fields={
                    "run_id": str(completed.id),
                    "tenant_id": completed.tenant_id,
                    "status": completed.status.value,
                },
            )
            return completed
        return run

    def _invoke_with_retry(
        self,
        handler: object,
        state: dict[str, object],
        step_context: StepContext,
        *,
        node: object,
        run: Run,
    ) -> object:
        from rath.definition import NodeSpec

        spec = cast(NodeSpec, node)
        last_error: BaseException | None = None
        for attempt in range(1, spec.retry.max_attempts + 1):
            try:
                callable_handler = cast(Any, handler)
                if spec.is_async:
                    value = callable_handler(
                        state,
                        step_context,
                    ) if spec.kind is not NodeKind.ROUTER else callable_handler(state)
                    assert inspect.isawaitable(value)
                    from rath._async.runtime import runtime as async_runtime

                    coroutine = cast(Coroutine[Any, Any, object], value)
                    if spec.timeout_seconds is not None:
                        import asyncio

                        coroutine = cast(
                            Coroutine[Any, Any, object],
                            asyncio.wait_for(coroutine, spec.timeout_seconds),
                        )
                    return async_runtime().run(coroutine)
                arguments = (
                    (state,)
                    if spec.kind is NodeKind.ROUTER
                    else (state, step_context)
                )
                if spec.timeout_seconds is None:
                    return callable_handler(*arguments)
                pool = ThreadPoolExecutor(max_workers=1)
                try:
                    future = pool.submit(callable_handler, *arguments)
                    return future.result(timeout=spec.timeout_seconds)
                finally:
                    pool.shutdown(wait=False, cancel_futures=True)
            except _RunSuspended:
                raise
            except BaseException as exc:
                last_error = exc
                self.store.append_run_event(
                    run.id,
                    "run.step.attempt.failed",
                    {
                        "node_id": spec.id,
                        "attempt": attempt,
                        "error_type": type(exc).__name__,
                    },
                )
                if attempt >= spec.retry.max_attempts:
                    raise
                delay = min(
                    spec.retry.max_seconds,
                    spec.retry.base_seconds * (2 ** (attempt - 1)),
                )
                time.sleep(delay)
        assert last_error is not None
        raise last_error

    def _heartbeat(
        self,
        claim: ClaimedRun,
        lease_seconds: float,
        stopped: threading.Event,
    ) -> None:
        interval = max(0.1, lease_seconds / 3)
        while not stopped.wait(interval):
            try:
                self.store.renew_lease(
                    claim.run.id,
                    worker_id=claim.lease.holder_worker_id,
                    fencing_token=claim.lease.fencing_token,
                    lease_seconds=lease_seconds,
                )
            except Exception:
                return

    def _forget_context_if_terminal(self, run: Run) -> None:
        if run.status in TERMINAL_RUN_STATUSES:
            self._contexts.pop(run.id, None)

    @staticmethod
    def _restore_context(run: Run) -> RunContext:
        raw = thaw_json(run.context)
        if not isinstance(raw, dict) or not raw:
            return RunContext(
                security=SecurityContext(
                    principal=Principal(
                        id="legacy-runtime-worker",
                        kind=PrincipalKind.SYSTEM,
                        claims={"context": "legacy-run"},
                    ),
                    tenant_id=run.tenant_id,
                ),
                revision_id=run.revision_id,
            )
        principal = raw["principal"]
        assert isinstance(principal, dict)
        deadline = raw.get("deadline")
        return RunContext(
            security=SecurityContext(
                principal=Principal(
                    id=str(principal["id"]),
                    kind=PrincipalKind(str(principal["kind"])),
                    claims=cast(
                        Mapping[str, JSONValue], principal.get("claims") or {}
                    ),
                ),
                tenant_id=run.tenant_id,
                project_id=(
                    str(raw["project_id"])
                    if raw.get("project_id") is not None
                    else None
                ),
                grants=frozenset(str(item) for item in raw.get("grants", [])),
                attributes=cast(
                    Mapping[str, JSONValue], raw.get("attributes") or {}
                ),
            ),
            revision_id=run.revision_id,
            request_id=UUID(str(raw["request_id"])),
            trace_context=TraceContext(
                trace_id=str(raw["trace_id"]),
                span_id=str(raw["span_id"]),
                sampled=bool(raw.get("sampled", True)),
            ),
            deadline=datetime.fromisoformat(str(deadline)) if deadline else None,
        )
