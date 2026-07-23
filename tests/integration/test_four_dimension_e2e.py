"""One pass over all four dimensions against the local backend.

Each test here is the honest question for its dimension: does the gate actually
refuse what the backend cannot do, does a denied tool call actually not run, does
the trajectory actually leave the building in a format someone else reads, and do
forked siblings actually become a preference pair.
"""

from __future__ import annotations

from typing import Any

from rath.backend import BackendCapability, get
from rath.benchmark import BenchmarkRunner, BenchmarkTask, CommandVerifier, gate_tasks
from rath.data import build_session_graph, extract_preference_pairs
from rath.env import EnvObservation, OpenRathEnvConfig, to_atif
from rath.flow.tool import ToolPolicy
from rath.session import Session


def _task(task_id: str, **kw: Any) -> BenchmarkTask:
    return BenchmarkTask(
        task_id=task_id,
        name=task_id,
        category="e2e",
        description="write solution.py",
        language="python",
        metric="pass",
        verifier=CommandVerifier(cmd="true"),
        internet=True,  # the local backend cannot enforce isolation
        **kw,
    )


def test_capability_gate_admits_only_what_the_backend_can_run() -> None:
    features = get("local").capabilities().features
    assert gate_tasks([_task("a")], features=features).coverage == 1.0

    offline = BenchmarkTask(
        task_id="offline",
        name="offline",
        category="e2e",
        description="d",
        language="python",
        metric="pass",
        verifier=CommandVerifier(cmd="true"),
        internet=False,
    )
    blocked = gate_tasks([offline], features=features)
    assert blocked.coverage == 0.0
    assert BackendCapability.NETWORK_ISOLATION in blocked.skipped[0].missing


def test_policy_denial_is_recorded_and_exports_as_atif() -> None:
    config = OpenRathEnvConfig(
        backend="local",
        max_steps=2,
        tool_policy=ToolPolicy(allow_tools=frozenset({"read_workspace_file"})),
    )
    runner = BenchmarkRunner(_task("policy"), env_config=config)

    asked: list[int] = []

    def _policy(task: BenchmarkTask, observation: EnvObservation | None) -> Any:
        if asked:
            return None
        asked.append(1)
        return {"tool_name": "run_shell_command", "arguments": {"cmd": "echo hi"}}

    result = runner.run(_policy, fail_fast=False)

    episode = result.trajectory_episode
    assert episode is not None
    step = episode.steps[0]
    assert step.status == "tool_failed"
    assert step.error is not None
    assert step.error["error_kind"] == "tool_policy_denied"

    # Dimension 1: the very same episode leaves the building as ATIF.
    document = to_atif(episode)
    assert document["schema_version"] == "ATIF-v1.7"
    call = document["steps"][0]["tool_calls"][0]
    assert call["function_name"] == "run_shell_command"
    assert document["steps"][0]["timestamp"] == step.created_at


def test_forked_sessions_yield_preference_pairs() -> None:
    parent = Session.from_user_message("root")
    good = parent.fork()
    bad = parent.fork()

    graph = build_session_graph(
        [parent, good, bad],
        rewards={str(good.id): 1.0, str(bad.id): 0.0},
        statuses={str(good.id): "completed", str(bad.id): "stopped"},
    )
    pairs = extract_preference_pairs(graph)

    assert len(pairs) == 1
    assert pairs[0].chosen == str(good.id)
    assert pairs[0].rejected == str(bad.id)
    assert pairs[0].parent_session_id == str(parent.id)
