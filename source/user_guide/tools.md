# Tools and ToolTable

## FlowToolCall hierarchy

`rath.flow.tool` defines immutable structured calls (`FlowToolCall`, aliasing
`BackendTool`):

| Constructor helper | Typical use |
|--------------------|-------------|
| `flow_tool_command_run` | Shell/command execution inside the sandbox |
| `flow_tool_files_read` / `flow_tool_files_write` | File IO |
| `flow_tool_files_list` / `flow_tool_files_exists` | Directory probes |
| `flow_tool_code_run` | Interpreter-backed execution when supported |

These mirror **functional** APIs: produce plain values consumed by backends.

## ToolTable

`ToolTable` stores `ToolRegistration` entries mapping OpenAI-style tool names to:

1. JSON Schema payloads surfaced to the LLM (`tools=[...]` wire format).
2. Callables that emit concrete `FlowToolCall` instances when the model selects a tool.

`global_tool_table()` returns the process-wide default; pass an explicit `tool_table`
to `run_session_loop` to scope registrations per workflow.

`register_builtin_session_tools(table)` loads stock filesystem/command/code helpers used by the session loop.

`register_global_tool` raises `ToolNameConflictError` if names collide—fail-fast registration semantics.

## Dispatch path

During `run_session_loop`:

1. Executor `tool_schemas()` advertises available tools (falls back to `table.schemas()`).
2. Assistant messages may contain tool calls.
3. Each call resolves through the table; executor `dispatch_tool` sends the resulting `FlowToolCall`
   to the active `BackendSandbox`.

Unsupported payloads surface as `UnsupportedBackendTool` from the backend layer.
