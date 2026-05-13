# Session Loop Tool Calls

After you have a Session and sandbox, the agent loop turns model tool calls into real tool execution. `run_session_loop(...)` appends an assistant row, executes tools, writes `tool_result`, and feeds the result into the next model request.

## Coverage
| Topic | Result |
| --- | --- |
| Request assembly | The agent Session comes first, followed by the user Session. |
| Tool schema | Built-in and custom tools are merged into the schema visible to the model. |
| Tool round | The assistant emits tool calls, then the loop executes tools and appends `tool_result`. |
| Output Session | The output Session inherits user-side rows and appends new rows. |
| Sandbox migration | The input Session's sandbox handle moves to the output Session. |

## Step 1: Prepare Agent and User Sessions
```python
from rath import flow
from rath.session import Session, run_session_loop

agent_session = Session.from_agent_prompt(
    "Use tools when the user asks for file work."
)
user_session = Session.from_user_message(
    "Create a file, then read it back."
).to("local")
provider = flow.Provider(api_key="sk-...", model="gpt-5.5")
```

Key lines:

| Line | Explanation |
| --- | --- |
| `Session.from_agent_prompt(...)` | Creates a system chunk for the agent-side Session. |
| `Session.from_user_message(...)` | Creates a user chunk for the user-side Session. |
| `.to("local")` | Binds the user Session to the local Backend so tools have an execution location. |
| `flow.Provider(...)` | Stores the model configuration for this request. |

## Step 2: Run the Loop
In real runs, `run_session_loop(...)` uses the default executor to issue an OpenAI-compatible request. Tests and tutorials can pass a scripted executor to make model responses deterministic.

```python
out = run_session_loop(
    user_session=user_session,
    agent_session=agent_session,
    agent_provider=provider,
    executor=scripted_executor,
)
```

The executor is responsible for two operations:

| Method | Purpose |
| --- | --- |
| `complete(req)` | Returns one chat completion response. |
| `dispatch_tool(session, tool, arguments)` | Executes the selected `FlowToolCall`. |

When no executor is passed, OpenRath creates `DefaultSessionLoopExecutor` and uses the default OpenAI-compatible client. In that mode, configure the model gateway through environment variables or `.env`.

## Step 3: Understand One Tool Round
When the model returns a tool call, the loop appends an assistant row, executes the tool, then appends a tool result row:

```text
user
assistant       contains tool_calls
tool_result     contains serialized tool output
assistant       final answer or next tool_calls
```

This ordering comes from `run_session_loop(...)`:

| Stage | What happens |
| --- | --- |
| Completion | The model returns an assistant message from the messages and tools. |
| Assistant row | If there is a tool call, the assistant row is added to `rows_list` first. |
| Dispatch | The loop finds the matching `FlowToolCall` and passes parsed arguments to it. |
| Tool result row | The tool result is serialized as JSON text and written to a `tool_result` chunk. |
| Next completion | The next request includes the earlier assistant row and tool result row. |

## Step 4: Inspect the Chunk Table
```python
for row in out.chunk_table.rows:
    print(row.kind, row.payload)
```

If the model writes a file and then reads it back, the typical order is:

```text
user
assistant       # write_workspace_file call
tool_result     # bytes_written
assistant       # run_shell_command call
tool_result     # command stdout / stderr
assistant       # final answer
```

Observed behavior:

- The `name` in the `tool_result` row matches the called tool name.
- The `content` in the `tool_result` row is the tool output visible to the next model round.
- The output Session still starts with user-side content; the agent system prompt is not copied into it.

## Step 5: Confirm Sandbox Migration
```python
sandbox = out.require_sandbox()
print(sandbox.backend.name)
```

`run_session_loop(...)` takes the sandbox handle from the input user Session and binds it to the output Session. If another agent or Workflow runs later, tools can still use the same sandbox.

## Troubleshooting
| Symptom | Check |
| --- | --- |
| Model did not call a tool | Check whether the system prompt, user prompt, and tool schema are explicit enough. |
| `unknown_tool` | The tool name returned by the model is not in the tool table. |
| `invalid_tool_arguments` | The model returned JSON arguments that could not be parsed. |
| Tool execution failed | Check the message and detail in `tool_execution_exception`. |
| Tool cannot find a sandbox | Confirm the user Session has already called `.to("local")` or `.with_sandbox(...)`. |

## Exercises
1. Change the user prompt to "Answer only; do not call tools" and observe whether `tool_result` still appears in the chunk table.
2. Pass a custom tool into `run_session_loop(...)` and confirm the tool table includes it.
3. Run `run_session_loop(...)` twice in sequence and confirm the second agent can see the `tool_result` left by the first agent.

## Summary

- `run_session_loop(...)` assembles agent/user messages and starts a completion.
- Built-in tools come from `global_system_tools()`, currently including `run_shell_command` and `write_workspace_file`.
- Tool results are serialized into `tool_result` chunks for the next LLM request.
- The output Session is the core object for continuing work in later Workflows.
