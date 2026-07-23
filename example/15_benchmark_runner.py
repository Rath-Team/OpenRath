"""15 · Benchmark runner — task metadata, policy actions, pytest verifier.

This is a small local analogue of long-horizon benchmark tasks: the task owns
metadata, an initial workspace, a verifier, and a max step budget. A policy
supplies structured tool actions until the verifier passes.
"""

from __future__ import annotations

import json

from rath.benchmark import BenchmarkRunner, BenchmarkTask, PytestVerifier
from rath.env import OpenRathEnvConfig, ToolAction


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
        max_steps=3,
    )


def main() -> None:
    task = build_task()

    def policy(_task, _observation):
        return ToolAction(
            tool_name="write_workspace_file",
            arguments={
                "path": "solution.py",
                "content": "def add_one(x):\n    return x + 1\n",
            },
        )

    runner = BenchmarkRunner(
        task,
        env_config=OpenRathEnvConfig(backend="local"),
    )
    result = runner.run(policy)
    report = result.to_jsonable()
    print(f"passed={result.passed} reward={result.reward} steps={result.steps}")
    print(json.dumps(report["verification"], indent=2, ensure_ascii=False)[:1200])
    print(
        json.dumps(
            report["trajectory_episode"]["steps"][0],
            indent=2,
            ensure_ascii=False,
        )[:1200]
    )


if __name__ == "__main__":
    main()
