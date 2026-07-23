"""14 · Trajectory collection — compact typed episode JSONL.

Runs offline with ``backend="local"``. Production collection should use the
default OpenSandbox backend for isolation.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from rath.backend import FileContent
from rath.env import (
    OpenRathEnv,
    OpenRathEnvConfig,
    RewardResult,
    ToolAction,
    load_trajectory_jsonl,
    materialize_trajectory,
)


def reward_fn(_session, action: ToolAction, raw_result) -> RewardResult:
    passed = (
        action.tool_name == "read_workspace_file"
        and isinstance(raw_result, FileContent)
        and raw_result.data == "DATA_OK"
    )
    return RewardResult(
        reward=1.0 if passed else 0.0,
        done=passed,
        info={"passed": passed},
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="openrath-trajectory-") as tmp:
        trajectory_path = Path(tmp) / "rollout.jsonl"
        env = OpenRathEnv(
            OpenRathEnvConfig(
                backend="local",
                reward_fn=reward_fn,
                trajectory_path=trajectory_path,
                max_steps=4,
            )
        )
        try:
            env.reset("Write DATA_OK to answer.txt, then verify it.")
            env.step(
                ToolAction(
                    tool_name="write_workspace_file",
                    arguments={"path": "answer.txt", "content": "DATA_OK"},
                )
            )
            final = env.step(
                ToolAction(
                    tool_name="read_workspace_file",
                    arguments={"path": "answer.txt"},
                )
            )

            episodes = load_trajectory_jsonl(trajectory_path)
            episode = episodes[0]
            transitions = materialize_trajectory(episode)
            print(f"trajectory_path={trajectory_path}")
            print(
                f"records={1 + len(episode.steps) + int(episode.end is not None)} "
                f"steps={len(episode.steps)} reward={final.reward} done={final.done}"
            )
            print(
                f"first_pre_chunks={len(transitions[0].observation.chunks)} "
                f"last_post_chunks={len(transitions[-1].next_observation.chunks)}"
            )
            print(episode.end.to_jsonable() if episode.end is not None else None)
        finally:
            env.close()


if __name__ == "__main__":
    main()
