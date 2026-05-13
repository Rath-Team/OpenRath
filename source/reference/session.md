(pkg-session)=
# `rath.session`

Session state, chunk transcript, session loop, context compression, and lineage graph.

## Source
| Module | Source |
| --- | --- |
| `rath.session.session` | `src/rath/session/session.py` |
| `rath.session.chunk` | `src/rath/session/chunk.py` |
| `rath.session.loop` | `src/rath/session/loop.py` |
| `rath.session.compress` | `src/rath/session/compress.py` |
| `rath.session.primitives` | `src/rath/session/primitives.py` |
| `rath.session.graph` | `src/rath/session/graph/` |
| `rath.session.manager` | `src/rath/session/manager.py` |

## Public contract
### `Session`

| Field | Type | Meaning |
| --- | --- | --- |
| `chunk_table` | `ChunkTable` | Chronological chunk rows. |
| `id` | `UUID` | Session identity. |
| `sandbox` | `BackendSandbox` \| `None` | Currently open sandbox handle. |
| `sandbox_backend` | `str` \| `None` | Backend name used for lazy open. |
| `parent_session_ids` | `tuple[UUID, ...]` | Lineage parents. |
| `lineage_operator` | `str` | Operation that produced the current session. |
| `lineage_kind` | `LineageKind` | Lineage operation kind. |

| Method | Returns | Behavior |
| --- | --- | --- |
| `Session.from_agent_prompt(prompt)` | `Session` | Creates a single `system` chunk. |
| `Session.from_user_message(text)` | `Session` | Creates a single `user` chunk. |
| `session.to(backend="local", spec=None)` | `Session` | Sets the sandbox target and closes the current handle. |
| `session.require_sandbox()` | `BackendSandbox` | Returns or lazily opens the current sandbox. |
| `session.take_sandbox()` | `BackendSandbox` | Takes the handle so the loop can attach it to the output session. |
| `session.fork()` | `Session` | Copies chunk rows and sandbox target, with the parent pointing to the source session. |
| `session.detach()` | `Session` | Copies chunk rows and sandbox target, then creates a new lineage root. |

### Chunk helpers
| Function | Returns | Purpose |
| --- | --- | --- |
| `user_text_chunk(text)` | `ChunkRow` | Creates a user row. |
| `system_text_chunk(text)` | `ChunkRow` | Creates a system row. |
| `assistant_turn_chunk(tool_calls, content=None)` | `ChunkRow` | Creates an assistant row. |
| `tool_feedback_chunk(tool_call_id, name, body)` | `ChunkRow` | Creates a tool result row. |
| `chunk_table_to_messages(tab)` | `tuple[RathLLMMessage, ...]` | Converts to chat completion messages. |

### Loop
```python
run_session_loop(
    user_session: Session,
    agent_session: Session,
    *,
    agent_provider: Provider,
    tools: list[FlowToolCall] | None = None,
    executor: SessionLoopExecutor | None = None,
    max_tool_rounds: int = 16,
) -> Session
```

| Parameter | Description |
| --- | --- |
| `user_session` | User-side transcript and sandbox placement. |
| `agent_session` | Agent/system transcript used in request assembly. |
| `agent_provider` | Model and request parameters. |
| `tools` | Additional `FlowToolCall` instances. |
| `executor` | Replacement point for completion and tool dispatch. |
| `max_tool_rounds` | Maximum number of tool-call rounds. |

The returned `Session` starts with the user rows, then appends assistant rows and `tool_result` rows. The output session lineage parents are the user session and agent session.

### Compression
```python
run_session_compress(
    user_session: Session,
    agent_session: Session,
    *,
    agent_provider: Provider,
    executor: SessionLoopExecutor | None = None,
    compress_instruction: str | None = None,
    register_sessions: bool = True,
) -> Session
```

Returns a user-only session. The compression request uses `tools=None` and `tool_choice="none"`. A model response with tool calls raises `RuntimeError`.

### Exceptions and edge behavior
| Location | Behavior |
| --- | --- |
| `Session.require_sandbox()` | Raises `RuntimeError` when no backend target is set. |
| `Session.take_sandbox()` | Raises `RuntimeError` when there is no sandbox and no backend target. |
| `run_session_loop(...)` | Non-JSON tool arguments, unknown tools, and tool execution exceptions are written as JSON error `tool_result` rows. |
| `run_session_compress(...)` | Empty model content, tool calls, and unexpected finish reasons raise `RuntimeError`. |

## Autodoc
```{eval-rst}
.. autoclass:: rath.session.Session
   :members:

.. autoclass:: rath.session.ChunkRow
   :members:

.. autoclass:: rath.session.ChunkTable
   :members:

.. autofunction:: rath.session.run_session_loop

.. autoclass:: rath.session.SessionLoopExecutor
   :members:

.. autofunction:: rath.session.run_session_compress

.. autofunction:: rath.session.create_leaf_user

.. autofunction:: rath.session.create_leaf_system

.. autofunction:: rath.session.fork_session

.. autofunction:: rath.session.detach_session
```

[← API Reference](index.md)
