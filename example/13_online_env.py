"""13 · Online Env — execute trainer actions without an LLM loop.

This example uses ``backend="local"`` so it runs offline. Production RL or HITL
jobs should use the default OpenSandbox backend for isolation.
"""

from __future__ import annotations

from rath.backend import CodeResult
from rath.env import OpenRathEnv, OpenRathEnvConfig, RewardResult, ToolAction


def reward_fn(_session, _action, raw_result) -> RewardResult:
    passed = (
        isinstance(raw_result, CodeResult)
        and raw_result.error is None
        and b"ONLINE_ENV_OK" in raw_result.stdout
    )
    return RewardResult(
        reward=1.0 if passed else 0.0,
        done=passed,
        info={"passed": passed},
    )


def main() -> None:
    env = OpenRathEnv(
        OpenRathEnvConfig(
            backend="local",
            reward_fn=reward_fn,
            max_steps=3,
            persist_trajectory=False,
        )
    )
    try:
        obs = env.reset("Print the marker ONLINE_ENV_OK.")
        print(f"session={obs.session_id}")

        result = env.step(
            ToolAction(
                tool_name="run_code",
                arguments={
                    "code": "print('ONLINE_ENV_OK')",
                    "language": "python",
                    "timeout": 2,
                },
            )
        )
        print(
            f"reward={result.reward} terminated={result.terminated} "
            f"truncated={result.truncated} info={result.info}"
        )
        print(f"latest={result.observation.latest_tool_result}")
        episode = env.trajectory_episode
        print(
            f"state={env.state} steps={episode.end.step_count if episode and episode.end else 0}"
        )
    finally:
        env.close()


if __name__ == "__main__":
    main()
