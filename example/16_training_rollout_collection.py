"""16 · Training rollout collection — batch trajectories for trainers.

This mirrors the part of RL infrastructure that prepares rollout batches for a
trainer. It does not train a model; it produces a dependency-free
``RolloutBatch`` that can be adapted to verl, TRL, Ray, or custom code.
"""

from __future__ import annotations

import json

from rath.benchmark import BenchmarkTask, PytestVerifier
from rath.env import OpenRathEnvConfig, ToolAction
from rath.training import collect_benchmark_rollouts


def build_task() -> BenchmarkTask:
    return BenchmarkTask(
        task_id="py_add_one",
        name="Python Add One",
        category="Systems & Software Engineering",
        description="Implement add_one(x) in solution.py so the tests pass.",
        language="Python",
        metric="pass rate",
        internet=False,
        initial_files={
            "solution.py": "def add_one(x):\n    return x\n",
            "test_solution.py": (
                "from solution import add_one\n\n"
                "def test_add_one():\n"
                "    assert add_one(41) == 42\n"
            ),
        },
        verifier=PytestVerifier(),
        max_steps=2,
    )


def main() -> None:
    task = build_task()

    def policy(_task, _observation):
        return ToolAction(
            "write_workspace_file",
            {"path": "solution.py", "content": "def add_one(x):\n    return x + 1\n"},
        )

    batch = collect_benchmark_rollouts(
        [task],
        policy,
        env_config=OpenRathEnvConfig(backend="local"),
        fail_fast=False,
        meta_info={"runner": "example"},
    )
    wire = batch.to_wire_payload()
    print(f"episodes={batch.num_episodes} steps={batch.num_steps}")
    print(json.dumps(batch.episodes[0].to_jsonable(), indent=2, ensure_ascii=False))
    print(json.dumps(wire["non_tensor_batch"]["statuses"], ensure_ascii=False))
    print(batch.trajectory_jsonl().splitlines()[0][:1200])

    # With ``openrath[verl]`` installed, call
    # ``rath.training.to_verl_data_proto(batch, tensors=tokenized_tensors)``
    # to construct an actual ``verl.protocol.DataProto``.


if __name__ == "__main__":
    main()
