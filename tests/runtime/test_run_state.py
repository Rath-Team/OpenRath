from __future__ import annotations

from uuid import uuid4

import pytest

from rath.runtime import (
    InvalidRunTransition,
    Run,
    RunStatus,
    assert_transition,
)


def _run(status: RunStatus = RunStatus.QUEUED) -> Run:
    return Run.create(
        plan_id=uuid4(),
        revision_id=uuid4(),
        session_id=uuid4(),
        tenant_id="tenant-1",
        status=status,
        state={"query": "hello"},
        next_nodes=("search",),
    )


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (RunStatus.QUEUED, RunStatus.RUNNING),
        (RunStatus.RUNNING, RunStatus.WAITING),
        (RunStatus.WAITING, RunStatus.QUEUED),
        (RunStatus.RUNNING, RunStatus.SUCCEEDED),
        (RunStatus.RUNNING, RunStatus.NEEDS_REVIEW),
        (RunStatus.NEEDS_REVIEW, RunStatus.QUEUED),
    ],
)
def test_valid_run_transitions(source: RunStatus, target: RunStatus) -> None:
    assert_transition(source, target)


def test_terminal_run_is_immutable() -> None:
    with pytest.raises(InvalidRunTransition):
        assert_transition(RunStatus.SUCCEEDED, RunStatus.RUNNING)


def test_run_state_is_deeply_immutable() -> None:
    state = {"nested": {"value": 1}}
    run = Run.create(
        plan_id=uuid4(),
        revision_id=uuid4(),
        session_id=uuid4(),
        tenant_id="tenant-1",
        state=state,
        next_nodes=("search",),
    )
    state["nested"]["value"] = 2

    assert run.state["nested"]["value"] == 1  # type: ignore[index]
    assert run.version == 0

