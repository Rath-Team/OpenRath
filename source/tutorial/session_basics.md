# Session Basics

The first questions in an agent Workflow are where state lives, where tools run, and how history is tracked. `Session` keeps those concerns in one object: `chunk_table` stores context, the Backend target decides where tools execute, and lineage fields record where the Session came from.

## Coverage

| Topic | Result |
| --- | --- |
| Create agent/user Sessions | System prompts and user messages become different chunk types. |
| Read the chunk table | `chunk_table.rows` is a time-ordered list of structured records. |
| Use fork and detach | Both copy the transcript, but they create different graph relationships. |
| Set the Backend target | `to("local")` only sets the target; the sandbox handle opens on demand. |
| Understand handle lifecycle | After the context manager exits, the current handle is closed. |

## Step 1: Create Agent and User Sessions

Start with two Sessions: one for the agent system prompt and one for the user input.

```python
from rath.session import Session

agent = Session.from_agent_prompt("You are a concise assistant.")
user = Session.from_user_message("List files in the sandbox.")

print(agent.chunk_table.rows[-1].kind)
print(user.chunk_table.rows[-1].kind)
print(user.chunk_table.rows[-1].payload["content"])
```

Key lines:

| Code | Purpose |
| --- | --- |
| `Session.from_agent_prompt(...)` | Creates a Session containing a `system` chunk. |
| `Session.from_user_message(...)` | Creates a Session containing a `user` chunk. |
| `chunk_table.rows[-1]` | Reads the latest chunk. |

Expected output:

```text
system
user
List files in the sandbox.
```

At this point neither Session has a sandbox target. They only store the transcript.

## Step 2: Understand the Chunk Table

`Session` does not store context as one large string. It stores a time-ordered table instead, so assistant tool calls and tool results keep their structure.

```python
for index, row in enumerate(user.chunk_table.rows):
    print(index, row.kind, row.payload)
```

For the newly created user Session, the output has one row:

```text
0 user {'content': 'List files in the sandbox.'}
```

Later, `run_session_loop(...)` appends assistant rows and tool result rows to this table. Each agent action becomes part of the Session history.

## Step 3: Preserve Origin with Fork

`fork()` is useful when you want to branch from the current state. It copies chunk rows and records the source Session as the parent.

```python
forked = user.fork()

print(forked.chunk_table.rows == user.chunk_table.rows)
print(forked.parent_session_ids == (user.id,))
print(forked.lineage_operator)
```

Expected output:

```text
True
True
Session.fork
```

Key points:

| Field | Meaning after fork |
| --- | --- |
| `chunk_table.rows` | Same content as the source Session. |
| `parent_session_ids` | Points to the source Session. |
| `lineage_operator` | The current implementation records `Session.fork`. |

Fork is commonly used for branching exploration. For example, the same user request can be sent to two Workflows, and the graph later shows that both came from the same input.

## Step 4: Create a New Starting Point with Detach

`detach()` also copies the transcript, but it makes the new Session a new lineage root.

```python
detached = forked.detach()

print(detached.chunk_table.rows == forked.chunk_table.rows)
print(detached.parent_session_ids)
print(detached.lineage_operator)
```

Expected output:

```text
True
()
Session.detach
```

Detach is useful when an intermediate state should become the entry point for a new task. The content is preserved, and graph parents are cleared.

## Step 5: Set the Local Backend Target

`to("local")` sets which Backend this Session will use later. It returns the same Session, so it can be chained.

```python
user.to("local")

print(user.sandbox_backend)
print(user.sandbox is None)
```

Expected output:

```text
local
True
```

`to("local")` sets the Backend target. It does not open a sandbox handle immediately. The handle opens on demand through `require_sandbox()`, `take_sandbox()`, or `with session:`.

## Step 6: Open and Close the Sandbox Handle

Use the context manager to open the sandbox when entering the block and close the current handle when leaving it.

```python
with user:
    sandbox = user.require_sandbox()
    print(sandbox.backend.name)
    print(user.sandbox is sandbox)
    print(sandbox.closed)

print(user.sandbox is None)
print(sandbox.closed)
```

Expected output:

```text
local
True
False
True
True
```

Key lines:

| Code | Purpose |
| --- | --- |
| `with user:` | Calls `_ensure_sandbox()` on entry and `close_sandbox()` on exit. |
| `require_sandbox()` | Returns the current handle; if no handle exists but a Backend target is set, it opens one lazily. |
| `sandbox.closed` | Marked as closed after the local Backend closes it. |

## Step 7: Fork Does Not Copy an Open Handle

If the source Session already has an open sandbox, the forked Session copies the Backend target but does not share the same open handle.

```python
source = Session.from_user_message("inspect").to("local")

with source:
    source_sandbox = source.require_sandbox()
    forked = source.fork()

    print(source.sandbox is source_sandbox)
    print(forked.sandbox is None)
    print(forked.sandbox_backend)
```

Expected output:

```text
True
True
local
```

An open sandbox handle has a lifecycle and side-effect boundary. `fork()` only copies the target for which Backend to open later; it does not copy an already open handle.

## Troubleshooting

| Symptom | Cause | Check |
| --- | --- | --- |
| `RuntimeError: no sandbox to take` | The Session has no Backend target and no handle. | Call `session.to("local")` or `with_sandbox(...)` first. |
| `session sandbox is closed` | The Session is bound to a closed handle. | Call `to(...)` again or bind a new sandbox. |
| Local workspace disappeared | `LocalBackend.close(...)` cleans up directories it manages. | Do not use important, non-reproducible directories as a local sandbox workspace. |
| No `sandbox` after fork | The current design copies only the Backend target. | Check `forked.sandbox_backend`. |

## Exercises

1. Change `user.to("local")` to `user.to("local", spec=".")` and observe which directory the sandbox handle points to.
2. Call `fork()` twice on the same `user`, then print each fork's `parent_session_ids`.
3. Write a file inside `with user:`, exit the context, and observe what happens to the workspace after the local Backend closes.

## Summary

- `Session` carries the transcript, Backend target, and lineage.
- `chunk_table` is a structured context table; later tool calls and tool results are appended to it.
- `fork()` copies content and preserves the parent; `detach()` copies content and creates a new graph root.
- `to(...)` sets the execution location; the sandbox handle opens on demand.
- `run_session_loop(...)` migrates the input user Session's sandbox to the output Session. Later tutorials cover that behavior.
