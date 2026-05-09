# Workflow and Agent

## Workflow

`Workflow` subclasses organize multi-agent orchestration:

1. Instantiate agents by assigning `Agent` instances to attributes (`self.planner`, …).
2. Implement `forward(self, session: Session) -> Session` (blocking).

Calling `workflow(session)` delegates to `forward`. `named_agents()` enumerates
registered `(name, agent)` pairs sorted by name, mirroring `nn.Module.named_children()`
style ergonomics.

`repr(workflow)` indents nested `Agent`/`Session` previews similarly to nested modules.

### Shortcut helper

`run_session_loop_from_agent` forwards keyword arguments from an `Agent` into
`run_session_loop` (mapping `agent_session`, `provider`, optional executor/tool table limits).

## Agent

`Agent` bundles:

| Field | Purpose |
|-------|---------|
| `agent_session` | Frozen-ish instructions (`Session`) concatenated **ahead** of user chunks inside `run_session_loop`. |
| `provider` | `Provider` dataclass carrying OpenAI-style sampling knobs (`model`, `temperature`, `tool_choice`, …). |

`Agent.data` exposes a read-only mapping view over both fields for debugging.

`Agent` **does not** own transports (`complete`) or sandbox dispatch—those stay inside a
`SessionLoopExecutor`.

## Session loop kernel

`run_session_loop(user_session, agent_session, *, agent_provider, executor=None, tool_table=None, max_tool_rounds=16)`

runs synchronously:

- Builds messages by concatenating `chunk_table_to_messages(agent_session)` with the evolving user-session rows.
- Issues completions via `executor.complete(RathLLMChatRequest(...))`.
- Executes parallel tool calls through `executor.dispatch_tool(session_snapshot, FlowToolCall)`.
- Appends assistant chunks plus serialized tool feedback chunks until no tools remain or rounds exhaust.

When `executor` is omitted, OpenRath constructs `DefaultSessionLoopExecutor(RathOpenAIChatClient(), tool_table=resolved_table)`
wrapping the default synchronous chat client configured via `.env` / environment variables.

See the repository file `example/workflow_usage.py` for a minimal pattern.
