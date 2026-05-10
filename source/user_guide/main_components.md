# OpenRath main components

The building blocks below mirror how PyTorch separates **data** (tensor),
**modules** (`nn.Module`), **functional ops**, and **device backends**—adapted to LLM
agents and sandboxed tools.

## Session

[`Session`](session) stores a [`ChunkTable`](session) plus optional sandbox binding.
Construct leaf sessions with helpers such as `Session.from_user_message` and
`Session.from_agent_prompt`, attach a backend with `.to(backend_name, spec=...)`,
and pass the session into `Workflow.forward` / `run_session_loop`.

## Workflow

[`Workflow`](workflow_agent) subclasses implement `forward(session) -> session`.
Assign [`AgentParam`](workflow_agent) instances as attributes to register them for
`named_agents()`—similar to registering child modules on `nn.Module`.

## AgentParam

[`AgentParam`](workflow_agent) pairs:

- `agent_session` — system / developer-facing chunks (`Session`),
- `provider` — [`Provider`](llm) sampling and routing fields folded into each completion request.

`AgentParam` intentionally excludes HTTP clients or executors; those belong to the session loop.

## run_session_loop

[`run_session_loop`](workflow_agent) alternates **chat completions** with **tool rounds**.
It concatenates `agent_session` chunks ahead of the mutable user-side rows seen by the model,
dispatches tool calls through a [`SessionLoopExecutor`](workflow_agent), and returns a new
`Session` carrying assistant and tool-result chunks. Sandbox ownership is rebased onto the
output session.

## ToolTable and FlowToolCall

[`ToolTable`](tools) maps OpenAI-style tool names to **sandbox** builders (`FlowToolCall`)
or **inline** `@tool` callables validated by Pydantic. There is a single process-wide
[`global_tool_table`](tools); `run_session_loop` always reads from it.

## Backends

[`BackendSandbox`](backends) is the runtime handle obtained when opening a sandbox.
[`Backend.dispatch`](backends) executes `BackendTool` payloads (aliases of `FlowToolCall`)
and returns typed results (`CommandResult`, `FileContent`, …).

Local and OpenSandbox adapters ship under `rath.backend.local` and
`rath.backend.opensandbox` (extra).

## LLM client

[`RathOpenAIChatClient`](llm) performs synchronous chat completions using environment-backed
settings (`python-dotenv`). [`DefaultSessionLoopExecutor`](workflow_agent) wraps the client,
implements `SessionLoopExecutor`, and bridges tool schemas to sandbox dispatch.
