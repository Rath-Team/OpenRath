# OpenRath RL and Evaluation Infrastructure

OpenRath provides four dependency-light layers for agent reinforcement learning
and evaluation:

1. compact trajectory collection;
2. sandbox-backed environment execution;
3. verifier-driven benchmark runs;
4. validated rollout batches and optional trainer adapters.

OpenRath is the rollout and data plane. It does not implement PPO, GRPO, DPO,
tokenization, advantages, backpropagation, a scheduler, or a remote rollout
service.

## Environment Contract

`OpenRathEnv` is an environment-style Python API, not an OpenAI Gym or
Gymnasium implementation. It has no Gym spaces and adds no Gym dependency.
Actors provide structured `ToolAction` values; the environment does not call an
LLM.

```python
from rath.env import OpenRathEnv, OpenRathEnvConfig, ToolAction

env = OpenRathEnv(OpenRathEnvConfig())
observation = env.reset("Create and verify answer.txt.")
step = env.step(
    ToolAction(
        "write_workspace_file",
        {"path": "answer.txt", "content": "done"},
    )
)
env.close()
```

`OpenRathEnvConfig()` defaults to `backend="opensandbox"`. There is no silent
fallback to the host. Use `backend="local"` only for tests, examples, and
trusted workloads.

The lifecycle is explicit:

- `NEW`: no episode is active;
- `RUNNING`: actions may execute;
- `DONE`: a normal terminal, max-step, or policy-stop end was recorded;
- `FAULTED`: a started action or lifecycle operation failed;
- `CLOSED`: the environment cannot be reset.

`StepResult` separates `terminated` from `truncated`; `done` is their derived
OR. Reaching `max_steps` truncates. A reward callback returning `done=True`
terminates. A policy stop leaves both flags false and is finalized through
`finish(status="stopped")` by the benchmark or collector layer.

`ToolAction`, `RewardResult`, and `EnvObservation` snapshot caller mappings and
reject unsupported or non-finite protocol values. `Path` and UUID values are
serialized as strings; bytes use an explicit base64 object.

## Transaction Semantics

`reset()` acquires a Session, sandbox, optional Session writer, compact
trajectory writer, and initial observation transactionally. A failed reset
releases every acquired resource and can be retried.

Once an action starts, its step index is never reused. If dispatch, reward,
verification, Session persistence, or trajectory persistence fails after the
workspace changes, OpenRath retains the action, available tool result, and
transcript delta in a failed `TrajectoryStep`. The environment then enters
`FAULTED`; callers must reset before another step.

Environment execution never calls `session_registry().register()` or
`set_active()`. Process-global active Session state is unchanged by reset,
step, finish, and close.

Shared tool instances follow `FlowToolCall` concurrency contracts across
environment and Session-loop callers. Unsafe tools serialize per instance;
parallel-safe tools serialize on `resource_key(arguments)`. Use
`tools_factory=` when each episode needs fresh mutable tool state.

Serializing per instance is deliberate: a tool object shared by two
environments may carry state of its own, and the dispatcher cannot know that it
does not. A tool that sets `sandbox_scoped = True` declares that it is
stateless and that the only resource it touches is the calling session's
sandbox; the dispatcher then narrows its lane to that sandbox, so unrelated
environments run it concurrently while two sessions sharing one sandbox still
take turns. The built-in tools set this. They have to: `global_system_tools()`
hands the same instance to every loop in the process, so a single shared lane
would make `run_shell_command` in one rollout wait for `run_shell_command` in
an unrelated one — and a user cannot substitute a fresh instance for a built-in
the way `tools_factory=` allows for their own tools.

## Session WAL and Trajectory JSONL

The two persistence planes serve different purposes:

- `persist_trajectory=True` enables the existing Session WAL under
  `.openrath/sessions/`. It stores complete conversation chunks for audit and
  Session replay.
- `trajectory_path=` writes compact, trainer-facing episode records. It stores
  one initial observation, per-action transcript deltas, and one episode end.

The compact schema is version 1:

```text
episode_start -> step* -> episode_end
```

Every record carries `schema_version`, `record_type`, and `episode_id`.
`TrajectoryStep` contains `action`, `transcript_delta`, `tool_result`, reward,
terminal flags, status, and structured error data. It does not duplicate full
pre/post observations. This keeps file growth linear in new transcript data.

```python
from rath.env import load_trajectory_jsonl, materialize_trajectory

episodes = load_trajectory_jsonl("rollouts.jsonl")
transitions = materialize_trajectory(episodes[0])
before = transitions[0].observation
after = transitions[0].next_observation
```

Normal terminal and intentional stop paths write `episode_end` and close the
Session WAL. Exceptional and replaced nonterminal episodes abandon the Session
WAL, leaving its partial-file crash signal. Compact output records a failed or
abandoned end when possible.

Overwrite exports are atomic. Append writes are locked. An environment that
streams to a shared trajectory path holds the append lock for its complete
episode so concurrent `start/step/end` records cannot interleave. This protects
cooperating writers; it is not a multi-file power-loss transaction. Prefer one
trajectory file per worker or shard at high scale, then concatenate complete
episodes offline.

## Benchmark Layer

`BenchmarkTask` keeps dataset metadata declarative while local Python objects
own executable setup and verification:

```python
from rath.benchmark import BenchmarkRunner, BenchmarkTask, PytestVerifier
from rath.env import OpenRathEnvConfig

task = BenchmarkTask(
    task_id="py_add_one",
    name="Python Add One",
    category="software_engineering",
    description="Implement add_one(x) in solution.py.",
    language="Python",
    metric="pass@1",
    initial_files={"solution.py": "def add_one(x):\n    return x\n"},
    verifier=PytestVerifier(),
    max_steps=8,
)

result = BenchmarkRunner(
    task,
    env_config=OpenRathEnvConfig(backend="local"),
).run(policy)
```

The metadata fields align with datasets such as EdgeBench: `task_id`, `name`,
`category`, `description`, `language`, `metric`, and `internet`.
`benchmark_tasks_from_jsonl()` reads these fields with strict path/line
diagnostics. Verifier and initial-file factories remain local; dataset JSON
never becomes executable configuration.

`PytestVerifier()` runs exactly `python -m pytest -q` inside the sandbox by
default. Override `python_command=` for images that expose another command.
A nonzero test exit is a normal `VerificationResult(passed=False)`. Backend,
startup, timeout, or incompatible-result failures raise
`VerifierExecutionError`.

Benchmark statuses identify the failed phase:

- `setup_failed`
- `policy_failed`
- `tool_failed`
- `verification_failed`
- `completed`
- `stopped`
- `max_steps`

Verification after an action contributes transition reward. Verification that
occurs without an action, including a zero-step run, contributes
`terminal_reward`. The runner does not repeat verification when the workspace
has not changed.

## Training Boundary

`RolloutBatch` owns grouped `EpisodeRollout` values:

```python
from rath.training import collect_benchmark_rollouts

batch = collect_benchmark_rollouts(
    tasks,
    policy,
    env_config=OpenRathEnvConfig(backend="opensandbox"),
    max_workers=8,
    max_in_flight=8,
    fail_fast=False,
)

wire = batch.to_wire_payload()
```

Each `EpisodeRollout` binds one `RolloutEpisode` summary to exactly one
`TrajectoryEpisode`. Constructors reject duplicate episode IDs, orphan or
non-contiguous steps, and summary/trajectory mismatches in reward, count,
status, or terminal flags. `select()`, `concat()`, and `make_iterator()` keep
that ownership intact.

Collectors consume input lazily. `max_in_flight` bounds how far they pull ahead
of completed work, while returned rollouts remain input-ordered. On fail-fast,
no new inputs are consumed after the first observed failure; pending futures
are cancelled and running environments finish cleanup before the original
error is raised. With `fail_fast=False`, setup, policy, environment, and
verifier failures become auditable rollouts retaining every executed step.

`to_wire_payload()` is a plain, framework-neutral payload. It is deliberately
not called `DataProto`.

## Optional verl Adapter

Install the tested adapter range on Python 3.10-3.12:

```bash
pip install 'openrath[verl]'
```

```python
from rath.training import to_verl_data_proto

data = to_verl_data_proto(
    batch,
    tensors=tokenized_tensors,
    non_tensors={"advantages_source": sources},
    meta_info={"run_id": run_id},
)
```

This returns a real `verl.protocol.DataProto` through
`DataProto.from_dict(tensors=..., non_tensors=..., meta_info=...)`. Canonical
episode fields are batch-aligned NumPy object arrays. Caller sequences must
match `batch.num_episodes` and cannot overwrite canonical OpenRath fields.

Core imports remain light: importing `rath.training` does not import verl,
PyTorch, NumPy, or TensorDict. The first tested extra is `verl>=0.8,<0.9` on
Python 3.10-3.12; OpenRath core continues to support Python 3.10-3.13.

## Security Boundary

Execution permissions belong to the sandbox/tool execution domain, not an
agent-wide default. Restrict command, filesystem, network, credentials,
timeouts, and mounts where tools dispatch. Benchmark metadata and policy input
must not grant broader authority. This keeps exploratory model behavior inside
the same enforceable boundary at every concurrency level.

Runnable local examples are `example/13_online_env.py` through
`example/16_training_rollout_collection.py`.
