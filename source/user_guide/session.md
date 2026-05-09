# Sessions and chunks

## Session

`Session` is the primary **conversation carrier**. It owns:

- **`chunk_table`** — ordered rows tagged by `ChunkKind` (`system`, `user`,
  `assistant`, `tool_result`, …).
- **Sandbox fields** — optional binding to a `BackendSandbox` plus the backend
  name used when the session was opened.

Factory helpers on `Session` include:

- `Session.from_user_message(text)` — seed a user turn without system preamble.
- `Session.from_agent_prompt(prompt)` — seed system/agent-side instructions.

## Binding a sandbox

Call `Session.to(backend_name, spec=...)` to open or rebind sandbox execution.
`spec` accepts a `BackendSandboxSpec` or a working-directory string interpreted
by the backend.

Downstream, `run_session_loop` **rebases** sandbox ownership onto the returned
session so tool dispatch targets the active workflow output.

## Chunk utilities

Module `rath.session` exports helpers such as `chunk_table_to_messages`,
`assistant_turn_chunk`, and `tool_feedback_chunk` for bridging chunk tables to LLM
wire formats inside the loop implementation.

## Lineage and registry

When graph tracking is enabled (`session_graph_mode()`), new sessions produced
by the loop are **stamped** with lineage metadata and registered through
`session_registry`. This enables provenance queries (`SessionLineage`, journal
helpers) analogous to tracking how intermediates were produced—without gradients.

## Primitives

`rath.session.primitives` exposes utilities such as `fork_session`,
`merge_sessions`, and `detach_session` for manipulating chunk histories. Treat
them as advanced building blocks until dedicated narratives land.
