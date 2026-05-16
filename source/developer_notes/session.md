# Session

`Session` is the main runtime object in OpenRath. Agent calls, tool calls, compression, and multi-agent handoffs all end up as changes to a `Session`.

This page explains how `Session` carries state, execution placement, and lineage, and how `fork()`, `detach()`, `run_session_loop(...)`, and `run_session_compress(...)` affect the session graph and sandbox handle.

Start with the diagram below: it shows the three pieces of state a session
carries, and the lifecycle operations that move or derive that state.

```{figure} ../_static/core-session.png
:alt: Session state overview

`Session` keeps conversation chunks, sandbox placement, and lineage metadata in
one object so that state can move through agent and workflow calls.
```

## Overview

`Session` is made of three kinds of state:

| Layer | Stored in | Purpose |
| --- | --- | --- |
| Conversation content | `chunk_table` | Which system/user/assistant/tool content the current agent can see. |
| Execution placement | `sandbox_backend`, `_sandbox_open_spec`, `sandbox` | Which backend receives tool side effects. |
| State origin | `id`, `parent_session_ids`, `lineage_kind` | Where this session came from and which operation produced it. |

These layers live in the same object because content state and execution state move together through an agent workflow. After one agent produces a tool call, later agents need to read the tool result and may continue using the same sandbox. `Session` is the value passed along that chain.

## Source map

| File | Responsibility |
| --- | --- |
| `src/rath/session/session.py` | `Session` dataclass, sandbox lifecycle, `fork()`, `detach()`. |
| `src/rath/session/chunk.py` | `ChunkKind`, `ChunkRow`, `ChunkTable`, and message conversion. |
| `src/rath/session/loop.py` | `run_session_loop(...)`, tool dispatch, `tool_result` writeback. |
| `src/rath/session/compress.py` | `run_session_compress(...)`. |
| `src/rath/session/graph/recording.py` | `LineageRecorder` and lineage mode. |
| `src/rath/session/graph/traverse.py` | Graph traversal and acyclic validation. |

## Why Context Is A Table

`Session.chunk_table` is a time-ordered tuple of `ChunkRow` values. Each row has a `kind` and a `payload`. This fits an agent runtime better than a single string because tool calls need structured data.

| Chunk kind | Key payload fields | Produced by | LLM message |
| --- | --- | --- | --- |
| `system` | `content` | `Session.from_agent_prompt(...)` | `role="system"` |
| `user` | `content` | `Session.from_user_message(...)` | `role="user"` |
| `assistant` | `content`, `tool_calls` | `run_session_loop(...)` | `role="assistant"` |
| `tool_result` | `tool_call_id`, `name`, `content` | After tool execution | `role="tool"` |

The key conversion happens in `chunk_table_to_messages(...)`:

```python
from rath.session import Session
from rath.session.chunk import chunk_table_to_messages

user = Session.from_user_message("List files.")
messages = chunk_table_to_messages(user.chunk_table)
print(messages[0].role)
print(messages[0].content)
```

The main constraint here is that OpenRath stores a replayable transcript. `tool_calls` in `assistant` rows and `tool_call_id` in `tool_result` rows are rebuilt into OpenAI-compatible messages on the next LLM request, so the model can see which tool it just called and what the tool returned.

## Agent Session And User Session

OpenRath stores the system prompt in an agent-side session and stores user input plus runtime results in a user-side session.

| Session | Typical content | Lifecycle |
| --- | --- | --- |
| agent session | `system` chunk | Held by `AgentParam` or `flow.Agent`, usually reused for many calls. |
| user session | `user`, `assistant`, `tool_result` chunks | A workflow call produces new sessions as it runs. |

When `run_session_loop(...)` builds a request, it places agent session messages before user session messages:

```text
request messages = agent_session rows + user_session rows
```

The output session starts from user-side rows and then appends assistant/tool rows. The system prompt is not copied into the output session. This keeps agent configuration separate from user runtime state: change the agent session and the same user session can enter a different behavior.

## Session graph

Every `Session` has an `id`. When an operation creates a new session, OpenRath records its origin in lineage fields.

| Field | Meaning |
| --- | --- |
| `id` | UUID of the current session. |
| `parent_session_ids` | Parent sessions that produced this session. |
| `lineage_operator` | Name of the operation that produced this session. |
| `lineage_kind` | Operation category, such as fork, detach, loop, or compress. |
| `lineage_extras` | Extra structured metadata. |

The graph explains how a run happened. In a multi-agent workflow, each agent receives the output session from the previous agent. In a nested workflow, child workflows also receive and return sessions. As long as each operation records its parents, the final result can be traced back through the steps that produced it.

## Five Primitives

Current `Session` changes can be understood through five primitives.

| Primitive | Code entry point | Content behavior | Graph behavior | Sandbox behavior |
| --- | --- | --- | --- | --- |
| create | `Session.from_user_message(...)`, `Session.from_agent_prompt(...)` | Creates a one-row transcript. | Classmethods default to `UNKNOWN`; `create_leaf_user(...)` and `create_leaf_system(...)` write leaf lineage. | No sandbox target. |
| fork | `session.fork()`, `fork_session(session)` | Copies chunk rows. | Parent points to the source session, `lineage_kind=OP_FORK`. | Copies the backend target, not the open handle. |
| detach | `session.detach()`, `detach_session(session)` | Copies chunk rows. | Parent is empty, `lineage_kind=OP_DETACH`. | Copies the backend target, not the open handle. |
| loop | `run_session_loop(user_session, agent_session, ...)` | Copies user rows and appends assistant/tool rows. | Parents are the user session and agent session. | Takes the sandbox from the input user session and binds it to the output session. |
| compress | `run_session_compress(user_session, agent_session, ...)` | Writes the model summary as a new user row. | Parents are the user session and agent session, with lossy compression metadata. | Takes the sandbox from the input user session and binds it to the output session. |

### When to use fork

Use `fork()` when multiple follow-up paths should start from the same state. For example, the same user request can be tried by two different workflows. The forked session keeps its parent, so the graph shows that it came from the original state.

### When to use detach

Use `detach()` when a transcript should become a fresh starting point. It preserves content and the backend target, but leaves graph parents empty. This is useful when intentionally cutting lineage, such as exporting an intermediate state as the entry point for a new task.

### When to use compress

Use `run_session_compress(...)` to turn a long transcript into a new user-side summary. It disables tool use and requires the model to return text only. In the current implementation, tool calls in the model response raise `RuntimeError`.

## Sandbox Lifecycle

`Session` stores both the sandbox target and the open handle.

| Field | Meaning |
| --- | --- |
| `sandbox_backend` | Backend name, such as `local` or `opensandbox`. |
| `_sandbox_open_spec` | Spec used to open the backend; string specs become `BackendSandboxSpec(working_dir=...)`. |
| `sandbox` | Open `BackendSandbox` handle. |

Common methods:

| Method | Behavior |
| --- | --- |
| `to("local", spec=...)` | Closes the current handle, sets the backend target, and returns the same session. |
| `bind_sandbox(sandbox)` | Releases the current handle (if any) and takes a reference on `sandbox` (refcount + 1). |
| `require_sandbox()` | Returns the current handle; if only a backend target exists, opens it lazily and acquires one reference. |
| `close_sandbox()` | Drops this session's reference; the backend closes the handle when the count reaches zero. |
| `fork()` / `detach()` / `merge(other)` | Duplicate the transcript and share the sandbox reference with the new session (refcount + 1). |

`fork()`, `detach()`, and `merge(other)` all share the open handle with the new session via `bind_sandbox`. `merge(other)` requires both sessions to share the same `BackendSandbox` (by identity) or both be unbound — otherwise it raises `ValueError`.

```python
from rath.session import Session

source = Session.from_user_message("Inspect project.").to("local")
with source:
    forked = source.fork()
    assert source.sandbox is forked.sandbox  # shared reference
    assert source.sandbox._refcount == 2
```

## run_session_loop State Transfer

`run_session_loop(...)` does four things:

1. Merges built-in tools with user-provided `FlowToolCall` objects.
2. Shares the input user session's sandbox with the output session (refcount + 1).
3. Runs LLM completions in a loop; if the assistant returns tool calls, executes tools and appends `tool_result`.
4. When there are no tool calls, appends the final assistant row and returns the output session.

The state transfer is:

| Location | Before loop | After loop |
| --- | --- | --- |
| Input user session | Holds original user rows and may hold a sandbox. | Sandbox unchanged; the input session keeps its reference. |
| agent session | Holds system rows. | Unchanged. |
| Output session | Does not exist. | Holds user rows, assistant rows, tool result rows, and a shared reference to the same sandbox. |

Tool errors do not directly stop the loop. The current implementation writes errors as JSON `tool_result` chunks and sends that result back to the model. There are three cases:

| Case | Written error kind |
| --- | --- |
| Tool arguments are not parseable JSON | `invalid_tool_arguments` |
| Model requested an unknown tool | `unknown_tool` |
| Tool execution raised an exception | `tool_execution_exception` |

## run_session_compress State Transfer

`run_session_compress(...)` uses the same agent/user session concatenation, but it creates a new user-only session.

| Behavior | Current implementation |
| --- | --- |
| Request content | agent session rows + user session rows + compression instruction. |
| tool choice | Tools are forced off. |
| Output content | Model text becomes the only `user` chunk. |
| sandbox | Shared with the output session via `bind_sandbox` (refcount + 1); the input keeps its reference. |
| lineage extras | `compression.lossy=True`, `compression.rows_out=1`. |

This operation is lossy. It reduces context length, and the compressed session keeps only the summary text written by the model.

## Code Reading Checkpoints

| Question | Where to look |
| --- | --- |
| How a row becomes an LLM message | `src/rath/session/chunk.py::chunk_table_to_messages` |
| When sandbox lazy open happens | `src/rath/session/session.py::_ensure_sandbox` |
| How loop shares the sandbox | `out.bind_sandbox(user_session.sandbox)` in `src/rath/session/loop.py::run_session_loop` |
| How compress disables tools | `default_tool_choice="none"` in `src/rath/session/compress.py::run_session_compress` |
| Whether fork/detach copy an open handle | `tests/session/test_session_fork_detach_merge.py` |

## Edge Cases

| Behavior | Current implementation |
| --- | --- |
| `require_sandbox()` without a backend target | Raises `RuntimeError` with guidance to call `session.to("local")` or `bind_sandbox(...)`. |
| `require_sandbox()` with a bound closed sandbox | Raises `RuntimeError("session sandbox is closed")`. |
| `fork()` / `detach()` / `merge()` | Copy chunk rows and share the source session's sandbox reference (refcount + 1). |
| `run_session_loop(...)` | Output session shares the input user session's sandbox reference (refcount + 1). |
| malformed tool arguments | Writes JSON error `tool_result` and continues the loop. |
| unknown tool | Writes JSON error `tool_result` and continues the loop. |
| tool exception | Catches the exception and writes JSON error `tool_result`. |
| compress tool calls | `run_session_compress(...)` raises `RuntimeError`. |

## Test Coverage

| Behavior | Tests |
| --- | --- |
| chunk to messages | `tests/session/test_chunk_messages.py` |
| sandbox lifecycle | `tests/session/test_session_sandbox_behavior.py` |
| fork/detach primitives | `tests/session/test_session_primitives.py`, `tests/session/test_session_fork_detach_merge.py` |
| loop with local backend | `tests/session/test_run_session_loop_local.py` |
| loop edge cases | `tests/session/test_run_session_loop_edges.py` |
| lineage graph | `tests/session/test_lineage_graph_unit.py` |
| live loop/compress | `tests/integration/test_session_loop_real.py`, `tests/integration/test_session_compress_real.py` |
