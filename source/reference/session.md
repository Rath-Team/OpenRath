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
| `rath.session.persistence` | `src/rath/session/persistence/` |

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
| `cumulative_usage` | `RathLLMTokenUsage` \| `None` | Running token usage accumulated by loop/compress and summed by `merge()`. |

| Method | Returns | Behavior |
| --- | --- | --- |
| `Session.from_agent_prompt(prompt)` | `Session` | Creates a single `system` chunk. |
| `Session.from_user_message(text)` | `Session` | Creates a single `user` chunk. |
| `session.to(backend="local", spec=None)` | `Session` | Sets the sandbox target and releases the current handle (refcount − 1). |
| `session.bind_sandbox(sandbox)` | `Session` | Releases the current handle and takes a reference on `sandbox` (refcount + 1). |
| `session.require_sandbox()` | `BackendSandbox` | Returns or lazily opens the current sandbox; acquires one reference on first open. |
| `session.close_sandbox()` | `Session` | Drops this session's reference; the backend closes when the count reaches zero. |
| `session.fork()` | `Session` | Copies chunk rows and shares the sandbox reference (refcount + 1); parent points to the source session. |
| `session.detach()` | `Session` | Copies chunk rows and shares the sandbox reference; creates a new lineage root. |
| `session.merge(other)` | `Session` | Concatenates `self.rows + other.rows`. Both inputs must share the same sandbox (by identity) or both be unbound; sums `cumulative_usage`. |

```{figure} ../_static/session-merge-lineage.png
:alt: Session merge lineage

`Session.merge(...)` joins compatible branches, preserves parent lineage, and
keeps sandbox ownership explicit.
```

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
    on_event: Callable[[RathLLMStreamDelta], None] | None = None,
    persist: bool = False,
    persist_path: Path | None = None,
    sandbox_handle_id: str | None = None,
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
| `on_event` | When set, each streamed `RathLLMStreamDelta` is forwarded here; the resolved chat client must satisfy `StreamingChatClient`. |
| `persist` / `persist_path` | When truthy, every appended chunk is written to `.openrath/sessions/<out.id>.jsonl` (or the explicit path). |
| `sandbox_handle_id` | Optional sandbox identifier persisted in the JSONL header for later reattach. |

The output session shares the input user session's sandbox reference (refcount + 1). The returned `Session` starts with the user rows, then appends assistant rows and `tool_result` rows. The output session lineage parents are the user session and agent session.

`executor` and `on_event` are mutually exclusive unless the caller manually wraps a streaming client in `StreamingExecutor`. When `on_event` is provided, the resolved client must implement `complete_stream(req)`; OpenAI supports this path, Anthropic currently does not.

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
    on_event: Callable[[RathLLMStreamDelta], None] | None = None,
    persist: bool = False,
    persist_path: Path | None = None,
    sandbox_handle_id: str | None = None,
) -> Session
```

Returns a user-only session. The compression request uses `tools=None` and `tool_choice="none"`. A model response with tool calls raises `RuntimeError`. `on_event` / `persist` behavior matches `run_session_loop`.

### Persistence
```{figure} ../_static/session-persistence-jsonl.png
:alt: Append-only session persistence JSONL

Session persistence writes a header, chunk records, and a trailer to JSONL; a
missing trailer marks an interrupted run.
```

| API | Behavior |
| --- | --- |
| `SessionWriter(session, path=None, sandbox_handle_id=None)` | Opens an append-only JSONL writer and writes a header. |
| `load_session(id, path=None)` | Parses a persisted session JSONL file into `PersistedSession`. |
| `list_persisted_sessions()` | Lists header metadata and closed/crashed state for stored sessions. |
| `delete_session(id)` | Deletes one persisted session file. |
| `prune_sessions(older_than=...)` | Deletes persisted sessions older than a cutoff. |
| `PersistedSession.to_resumable_pair(agent_prompt=None)` | Builds `(user_session, agent_session)` for another loop call without opening a sandbox. |

Persistence records are newline-delimited JSON:

| Record | Meaning |
| --- | --- |
| `header` | Session id, lineage, sandbox backend/spec, optional sandbox handle id. |
| `chunk` | One appended chunk row. Inherited user rows are seeded before new loop output rows. |
| `trailer` | Graceful close marker plus final cumulative usage. Missing trailer means the process likely crashed mid-write. |

### Lineage export
| API | Behavior |
| --- | --- |
| `session_to_jsonl_row(session)` | Projects one session into a JSON-ready lineage row. |
| `export_jsonl_string(sessions)` | Returns JSONL for an iterable of sessions. |
| `export_jsonl(sessions, path)` | Writes lineage JSONL to disk. |
| `export_journal_jsonl(journal, path, skip_unknown=True)` | Resolves `LineageJournal.visit_order` through the registry and exports rows. |

### Exceptions and edge behavior
| Location | Behavior |
| --- | --- |
| `Session.require_sandbox()` | Raises `RuntimeError` when no backend target is set. |
| `Session.merge(other)` | Raises `ValueError` when the two sessions reference different sandboxes (or different backend targets, when both unbound). |
| `run_session_loop(on_event=...)` | Raises `TypeError` upfront when the resolved chat client does not implement `complete_stream(req)`. |
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

.. autoclass:: rath.session.loop.StreamingExecutor
   :members:

.. autofunction:: rath.session.run_session_compress

.. autofunction:: rath.session.create_leaf_user

.. autofunction:: rath.session.create_leaf_system

.. autofunction:: rath.session.fork_session

.. autofunction:: rath.session.detach_session

.. autoclass:: rath.session.SessionWriter
   :members:

.. autofunction:: rath.session.load_session

.. autofunction:: rath.session.list_persisted_sessions

.. autofunction:: rath.session.delete_session

.. autofunction:: rath.session.prune_sessions

.. autoclass:: rath.session.PersistedSession
   :members:

.. autoclass:: rath.session.PersistedSessionHeader
   :members:

.. autoclass:: rath.session.PersistedSessionMeta
   :members:

.. autoexception:: rath.session.PersistenceError

.. autofunction:: rath.session.graph.export.session_to_jsonl_row

.. autofunction:: rath.session.graph.export.export_jsonl_string

.. autofunction:: rath.session.graph.export.export_jsonl

.. autofunction:: rath.session.graph.export.export_journal_jsonl
```

[← API Reference](index.md)
