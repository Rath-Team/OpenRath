from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any
from uuid import UUID

from rath.backend import get
from rath.benchmark import BenchmarkRunner, BenchmarkTask, PytestVerifier
from rath.env import (
    OpenRathEnvConfig,
    ToolAction,
    load_trajectory_jsonl,
    materialize_trajectory,
    write_trajectory_jsonl,
)
from rath.session import session_registry
from rath.session.persistence.paths import session_file, session_partial_file
from rath.training import (
    EpisodeRollout,
    RolloutBatch,
    RolloutEpisode,
    to_verl_data_proto,
)


class _FakeArray(list[Any]):
    pass


def test_local_rl_infrastructure_pipeline_end_to_end(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OPENRATH_HOME", str(tmp_path / "openrath-home"))
    compact_path = tmp_path / "streamed.jsonl"
    export_path = tmp_path / "exported.jsonl"
    registry_before = session_registry().get_active_id()
    backend = get("local")
    sandboxes_before = backend.sandbox_count()

    task = BenchmarkTask(
        task_id="e2e_add_one",
        name="E2E Add One",
        category="software",
        description="Implement add_one.",
        language="Python",
        metric="pass@1",
        initial_files={
            "solution.py": "def add_one(x):\n    return x\n",
            "test_solution.py": (
                "from solution import add_one\n"
                "def test_add_one(): assert add_one(41) == 42\n"
            ),
        },
        verifier=PytestVerifier(),
        max_steps=2,
    )
    result = BenchmarkRunner(
        task,
        env_config=OpenRathEnvConfig(
            backend="local",
            persist_trajectory=True,
            trajectory_path=compact_path,
        ),
    ).run(
        lambda _task, _observation: ToolAction(
            "write_workspace_file",
            {
                "path": "solution.py",
                "content": "def add_one(x):\n    return x + 1\n",
            },
        )
    )

    assert result.passed
    assert result.verification.info["exit_code"] == 0  # type: ignore[union-attr]
    assert result.trajectory_episode is not None
    write_trajectory_jsonl(result.trajectory_episode, export_path)
    loaded = load_trajectory_jsonl(export_path)
    streamed = load_trajectory_jsonl(compact_path)
    assert loaded == streamed
    transitions = materialize_trajectory(loaded[0])
    assert transitions[-1].next_observation == loaded[0].end.final_observation  # type: ignore[union-attr]

    end = loaded[0].end
    assert end is not None
    summary = RolloutEpisode(
        episode_id=loaded[0].episode_id,
        task_id=task.task_id,
        reward=end.total_reward,
        terminated=end.terminated,
        truncated=end.truncated,
        steps=len(loaded[0].steps),
        status=end.status,
    )
    batch = RolloutBatch((EpisodeRollout(summary, loaded[0]),), {"run": "e2e"})
    wire = batch.to_wire_payload()
    assert wire["non_tensor_batch"]["episode_ids"] == [loaded[0].episode_id]

    numpy = types.ModuleType("numpy")
    numpy.empty = lambda size, dtype=None: _FakeArray([None] * size)  # type: ignore[attr-defined]
    verl = types.ModuleType("verl")
    verl.__version__ = "0.8.0"  # type: ignore[attr-defined]
    protocol = types.ModuleType("verl.protocol")

    class DataProto:
        @classmethod
        def from_dict(cls, **kwargs: Any) -> "DataProto":
            instance = cls()
            instance.payload = kwargs
            return instance

    protocol.DataProto = DataProto  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "numpy", numpy)
    monkeypatch.setitem(sys.modules, "verl", verl)
    monkeypatch.setitem(sys.modules, "verl.protocol", protocol)
    data_proto = to_verl_data_proto(batch)
    assert isinstance(data_proto, DataProto)
    assert data_proto.payload["meta_info"]["openrath_num_episodes"] == 1

    episode_id = loaded[0].episode_id
    assert session_file(episode_id).is_file()
    assert not session_partial_file(episode_id).exists()
    assert backend.sandbox_count() == sandboxes_before
    assert session_registry().get_active_id() == registry_before
    assert (
        session_registry().get(
            UUID(result.trajectory_episode.start.initial_observation.session_id)
        )
        is None
    )
