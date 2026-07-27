"""Persistence protocol shared by embedded and production Run stores."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from rath.runtime.models import (
    ApprovalDecision,
    Checkpoint,
    ClaimedRun,
    Interrupt,
    ResourceLease,
    Run,
    RunEvent,
    RunStatus,
)

__all__ = ["RunStore"]


@runtime_checkable
class RunStore(Protocol):
    def create_run(self, run: Run) -> Run: ...

    def get_run(self, run_id: UUID) -> Run: ...

    def list_runs(self, *, tenant_id: str) -> tuple[Run, ...]: ...

    def transition_run(
        self,
        run_id: UUID,
        *,
        expected_version: int,
        target: RunStatus,
        state: Mapping[str, object] | None = None,
        next_nodes: tuple[str, ...] | None = None,
    ) -> Run: ...

    def list_run_events(self, run_id: UUID) -> tuple[RunEvent, ...]: ...

    def append_checkpoint(self, checkpoint: Checkpoint) -> None: ...

    def latest_checkpoint(self, run_id: UUID) -> Checkpoint | None: ...

    def create_interrupt(
        self,
        interrupt: Interrupt,
        *,
        expected_run_version: int,
    ) -> Run: ...

    def get_interrupt(self, interrupt_id: UUID) -> Interrupt: ...

    def decide_interrupt(
        self,
        interrupt_id: UUID,
        *,
        decision: ApprovalDecision,
        expected_run_version: int,
    ) -> Run: ...

    def claim_next(
        self,
        *,
        worker_id: str,
        lease_seconds: float,
        now: datetime | None = None,
    ) -> ClaimedRun | None: ...

    def renew_lease(
        self,
        run_id: UUID,
        *,
        worker_id: str,
        fencing_token: int,
        lease_seconds: float,
        now: datetime | None = None,
    ) -> ResourceLease: ...

    def assert_fencing_token(
        self,
        run_id: UUID,
        *,
        worker_id: str,
        fencing_token: int,
    ) -> None: ...

    def requeue_expired_leases(
        self,
        *,
        now: datetime | None = None,
    ) -> tuple[UUID, ...]: ...

    def close(self) -> None: ...
