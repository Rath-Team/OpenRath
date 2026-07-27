"""Embedded durable executor for explicit Workflow step boundaries."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Coroutine, cast
from uuid import UUID

from rath._json import thaw_json
from rath.context import RunContext
from rath.definition import ExecutionPlan, NodeKind, WorkflowCompiler
from rath.observability import GuardedTelemetry, NoOpTelemetry, Telemetry
from rath.runtime.models import Checkpoint, ClaimedRun, Run, RunStatus
from rath.runtime.sqlite import SQLiteRunStore

__all__ = ["LocalRuntime", "StepContext"]


@dataclass(frozen=True, slots=True)
class StepContext:
    run_id: UUID
    request: RunContext
    worker_id: str
    fencing_token: int


@dataclass(frozen=True, slots=True)
class _Registration:
    workflow: object
    plan: ExecutionPlan


class LocalRuntime:
    """Sync façade over the durable local worker engine."""

    def __init__(
        self,
        store: SQLiteRunStore,
        *,
        telemetry: Telemetry | None = None,
    ) -> None:
        self.store = store
        self.telemetry = GuardedTelemetry(telemetry or NoOpTelemetry())
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
        )
        created = self.store.create_run(run)
        self._contexts[created.id] = context
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
        try:
            return self._execute_claim(claim, max_steps=max_steps)
        except BaseException as exc:
            return self.store.finish_claim(
                claim.run.id,
                worker_id=worker_id,
                fencing_token=claim.lease.fencing_token,
                expected_run_version=self.store.get_run(claim.run.id).version,
                target=RunStatus.FAILED,
                event_type="run.execution.failed",
                event_data={
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
            )

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
            context = RunContext.local(revision_id=claim.run.revision_id)
        run = claim.run
        steps = 0
        by_id = {node.id: node for node in registration.plan.nodes}
        while run.next_nodes and (max_steps is None or steps < max_steps):
            node_id = run.next_nodes[0]
            node = by_id[node_id]
            state_value = thaw_json(run.state)
            assert isinstance(state_value, dict)
            handler = getattr(registration.workflow, node.id)
            step_context = StepContext(
                run_id=run.id,
                request=context,
                worker_id=claim.lease.holder_worker_id,
                fencing_token=claim.lease.fencing_token,
            )
            with self.telemetry.span(
                "openrath.node",
                context=context.trace_context,
                attributes={"run_id": str(run.id), "node_id": node.id},
            ):
                if node.kind is NodeKind.ROUTER:
                    result = handler(state_value)
                else:
                    result = handler(state_value, step_context)
                if inspect.isawaitable(result):
                    from rath._async.runtime import runtime as async_runtime

                    result = async_runtime().run(
                        cast(Coroutine[Any, Any, object], result)
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

            latest = self.store.latest_checkpoint(run.id)
            checkpoint = Checkpoint.create(
                run_id=run.id,
                sequence=1 if latest is None else latest.sequence + 1,
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
            return self.store.finish_claim(
                run.id,
                worker_id=claim.lease.holder_worker_id,
                fencing_token=claim.lease.fencing_token,
                expected_run_version=run.version,
                target=RunStatus.SUCCEEDED,
            )
        return run
