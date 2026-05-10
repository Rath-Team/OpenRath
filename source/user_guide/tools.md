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

## Global ToolTable

`global_tool_table()` is the **single** registry used by `run_session_loop`. Default
sandbox-loop tools (`run_shell_command`, `write_workspace_file`) are installed the
first time the global table is accessed (including when you `import rath.flow.tool`).

`extend_builtin_sandbox_tools(table)` reapplies those defaults onto any `ToolTable`
(useful for isolated tests).

## Inline tools — `@tool`

`tool(...)` (LangChain-style) registers a **Python** callable with a Pydantic
`args_schema`. When the model selects that tool, arguments are validated with Pydantic
and the function runs **in-process** inside `run_session_loop` (not via the sandbox).
Use sandbox `ToolRegistration` builders when execution must happen on `BackendSandbox`.

`register_global_tool` raises `ToolNameConflictError` if names collide.

## ToolRegistration

Entries are either:

1. **Sandbox** — `builder(args) -> FlowToolCall`, explicit JSON Schema `parameters`.
2. **Inline** — `inline_fn` + `args_schema` (`type[pydantic.BaseModel]`); schema for the LLM
   usually comes from `args_schema.model_json_schema()`.

Use `ToolTable.resolve(name, arguments)` for both kinds; `ToolTable.build` accepts **sandbox**
tools only.

## Dispatch path

During `run_session_loop`:

1. Tool definitions come from `global_tool_table()`; executor `tool_schemas()` may override the advertised list.
2. Assistant messages may contain tool calls.
3. Each call is **resolved** through the table; **sandbox** resolutions go to `executor.dispatch_tool` → `BackendSandbox.dispatch`; **inline** resolutions call the registered Python function and JSON-serialize the return value for the model.

Unsupported sandbox payloads surface as `UnsupportedBackendTool` from the backend layer.
