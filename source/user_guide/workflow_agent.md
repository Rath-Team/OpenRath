# Workflow and AgentParam

## Workflow

`Workflow` subclasses organize multi-agent orchestration:

1. Instantiate agent params by assigning `AgentParam` instances to attributes (`self.planner`, …).
2. Implement `forward(self, session: Session) -> Session` (blocking).

Calling `workflow(session)` delegates to `forward`. `named_agents()` enumerates
registered `(name, agent)` pairs sorted by name, mirroring `nn.Module.named_children()`
style ergonomics.

`repr(workflow)` indents nested `AgentParam`/`Session` previews similarly to nested modules.

### Shortcut helper

`run_session_loop_from_agent` forwards keyword arguments from an `AgentParam` into
`run_session_loop` (mapping `agent_session`, `provider`, optional executor and round limits).

## AgentParam

`AgentParam` bundles:

| Field | Purpose |
|-------|---------|
| `agent_session` | Frozen-ish instructions (`Session`) concatenated **ahead** of user chunks inside `run_session_loop`. |
| `provider` | `Provider` dataclass carrying OpenAI-style sampling knobs (`model`, `temperature`, `tool_choice`, …). |

`AgentParam.data` exposes a read-only mapping view over both fields for debugging.

`AgentParam` **does not** own transports (`complete`) or sandbox dispatch—those stay inside a
`SessionLoopExecutor`.

## Session loop kernel

`run_session_loop(user_session, agent_session, *, agent_provider, executor=None, max_tool_rounds=16)`

runs synchronously:

- Builds messages by concatenating `chunk_table_to_messages(agent_session)` with the evolving user-session rows.
- Issues completions via `executor.complete(RathLLMChatRequest(...))`.
- Resolves each tool call via `global_tool_table().resolve(...)`: **sandbox** tools use `executor.dispatch_tool(session_snapshot, FlowToolCall)`; **inline** `@tool` functions run in-process and results are serialized for the model.
- Appends assistant chunks plus serialized tool feedback chunks until no tools remain or rounds exhaust.

When `executor` is omitted, OpenRath constructs `DefaultSessionLoopExecutor(RathOpenAIChatClient())`
wrapping the default synchronous chat client configured via `.env` / environment variables.

See the repository file `example/workflow_usage.py` for a minimal pattern.
