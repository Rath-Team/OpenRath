"""Embedded durable executor for explicit Workflow step boundaries."""

from __future__ import annotations

import threading
from asyncio import TimeoutError as AsyncTimeoutError
from collections.abc import Callable, Mapping
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import cast
from uuid import UUID

from rath._json import JSONValue, freeze_mapping, thaw_json
from rath.adapters.schema import validate_json
from rath.context import DeadlineExceededError, RunContext, TraceContext
from rath.definition import ExecutionPlan, NodeKind, WorkflowCompiler
from rath.observability import (
    GuardedTelemetry,
    NoOpTelemetry,
    StructuredLogger,
    Telemetry,
)
from rath.runtime.effects import (
    EffectLedger,
    Reconciliation,
    reconcile_stale_effects,
)
from rath.runtime.execution import (
    ExecutionServices,
    PythonStepExecutor,
    StepExecutor,
    StepSuspended,
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

__all__ = ["LocalRuntime", "PlanMismatchError", "StepContext"]


class PlanMismatchError(RuntimeError):
    """A durable checkpoint does not belong to the registered executable plan."""


@dataclass(frozen=True, slots=True)
class StepContext:
    run_id: UUID
    request: RunContext
    worker_id: str
    fencing_token: int
    policy_manifest: Mapping[str, JSONValue]
    services: ExecutionServices | None
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
        effect_ledger: EffectLedger | None = None,
        production_mode: bool = False,
        execution_services: ExecutionServices | None = None,
        step_executor: StepExecutor | None = None,
    ) -> None:
        self.store = store
        self.telemetry = GuardedTelemetry(telemetry or NoOpTelemetry())
        self.structured_logger = structured_logger or StructuredLogger()
        if (
            effect_ledger is not None
            and execution_services is not None
            and effect_ledger is not execution_services.effects
        ):
            raise ValueError(
                "effect_ledger and execution_services.effects must be identical"
            )
        self.execution_services = execution_services
        self.effect_ledger = (
            effect_ledger
            if effect_ledger is not None
            else execution_services.effects
            if execution_services is not None
            else None
        )
        self.production_mode = production_mode
        self.step_executor = step_executor or PythonStepExecutor(store)
        self._registrations: dict[UUID, _Registration] = {}
        self._contexts: dict[UUID, RunContext] = {}

    def register(self, workflow: object, *, revision_id: UUID) -> ExecutionPlan:
        plan = WorkflowCompiler().compile(
            workflow,
            revision_id=revision_id,
            production_durable=self.production_mode,
            input_schema=getattr(workflow, "input_schema", None),
            state_schema=getattr(workflow, "state_schema", None),
            policy_manifest=getattr(workflow, "policy_manifest", None),
        )
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
        input_state = state or {}
        if plan.definition.input_schema:
            validate_json(input_state, plan.definition.input_schema)
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
                    context.deadline.isoformat()
                    if context.deadline is not None
                    else None
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
        except StepSuspended:
            waiting = self.store.get_run(claim.run.id)
            self.structured_logger.emit(
                "run.suspended",
                context=(
                    claim_context.trace_context if claim_context is not None else None
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
            try:
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
            except ConflictError:
                # Lease loss/fencing means this worker no longer owns the right
                # to publish a terminal result. Recovery will reconcile effects
                # and requeue the durable Run under a new fencing token.
                return self.store.get_run(claim.run.id)
            self.structured_logger.emit(
                "run.failed",
                context=(
                    claim_context.trace_context if claim_context is not None else None
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
        latest_checkpoint = self.store.latest_checkpoint(run.id)
        if (
            latest_checkpoint is not None
            and latest_checkpoint.plan_hash != registration.plan.definition_hash
        ):
            raise PlanMismatchError(
                "checkpoint plan hash does not match registered execution plan"
            )
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
                        and existing.request.get("_openrath_checkpoint_sequence")
                        == checkpoint_sequence
                    ):
                        if existing.decision is None:
                            raise StepSuspended("run is waiting for a decision")
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
                raise StepSuspended("run was suspended for a decision")

            step_context = StepContext(
                run_id=run.id,
                request=context,
                worker_id=claim.lease.holder_worker_id,
                fencing_token=claim.lease.fencing_token,
                policy_manifest=registration.plan.policy_manifest,
                services=self.execution_services,
                _interrupt_handler=request_interrupt,
            )
            with self.telemetry.span(
                "openrath.node",
                context=context.trace_context,
                attributes={"run_id": str(run.id), "node_id": node.id},
            ):
                result = self.step_executor.execute(
                    handler=handler,
                    state=state_value,
                    context=step_context,
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
                    raise TypeError(f"step {node.id!r} must return a mapping or None")
                if len(node.successors) > 1:
                    raise ValueError(
                        f"step {node.id!r} has multiple successors; use @router"
                    )
                next_nodes = node.successors

            if registration.plan.definition.state_schema:
                validate_json(
                    next_state,
                    registration.plan.definition.state_schema,
                )

            if node.checkpoint or not next_nodes:
                checkpoint = Checkpoint.create(
                    run_id=run.id,
                    sequence=checkpoint_sequence,
                    plan_hash=registration.plan.definition_hash,
                    state=next_state,
                    next_nodes=next_nodes,
                    effect_watermark=(
                        self.effect_ledger.watermark(run.id)
                        if self.effect_ledger is not None
                        else 0
                    ),
                )
                run = self.store.commit_checkpoint(
                    checkpoint,
                    worker_id=claim.lease.holder_worker_id,
                    fencing_token=claim.lease.fencing_token,
                    expected_run_version=run.version,
                )
            else:
                run = replace(
                    run,
                    state=freeze_mapping(next_state, field="run.state"),
                    next_nodes=next_nodes,
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

    def reconcile_effects(
        self,
        *,
        grace_seconds: float = 30.0,
        now: datetime | None = None,
    ) -> Reconciliation:
        if self.effect_ledger is None:
            return Reconciliation((), ())
        return reconcile_stale_effects(
            self.effect_ledger,
            self.store,
            grace_seconds=grace_seconds,
            now=now,
        )

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
                    claims=cast(Mapping[str, JSONValue], principal.get("claims") or {}),
                ),
                tenant_id=run.tenant_id,
                project_id=(
                    str(raw["project_id"])
                    if raw.get("project_id") is not None
                    else None
                ),
                grants=frozenset(str(item) for item in raw.get("grants", [])),
                attributes=cast(Mapping[str, JSONValue], raw.get("attributes") or {}),
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
