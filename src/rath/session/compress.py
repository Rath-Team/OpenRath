"""Session context compression via one-shot LLM call (:func:`run_session_compress`)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from rath.llm import (
    Provider,
    RathLLMChatResponse,
    RathLLMMessage,
    RathLLMStreamDelta,
    add_usage,
)
from rath.session.chat_request_build import provider_into_chat_request
from rath.session.chunk import ChunkTable, chunk_table_to_messages, user_text_chunk
from rath.session.graph import LineageKind, LineageRecorder, SessionLineage
from rath.session.loop import SessionLoopExecutor, resolve_executor
from rath.session.manager import session_registry
from rath.session.persistence import SessionWriter
from rath.session.session import Session

_DEFAULT_COMPRESS_INSTRUCTION = (
    "The messages above are a conversation transcript (system/agent context followed "
    "by user-visible turns). Compress them into a shorter narrative that preserves "
    "facts, user goals, and open tasks. Output plain text only, suitable as the "
    "sole replacement user-side transcript — no role labels."
)


def run_session_compress(
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
) -> Session:
    """Summarize transcript via LLM into a new user-only session (no SYSTEM chunks).

    ``agent_session`` and ``user_session`` chunks are folded into the completion
    request only — they are not copied into ``out.chunk_table``. The returned session
    contains a single **USER** row built from the model reply.

    Completions use ``tools=None`` and ``tool_choice=none``. If the model returns tool
    calls, raises ``RuntimeError``.

    When ``executor`` is ``None``, a default executor is built from
    ``agent_provider``; it must carry a non-empty ``api_key``.

    Shares the ``BackendSandbox`` from ``user_session`` with the returned
    session (refcount + 1) when one is bound; the user session keeps its
    reference.

    When ``on_event`` is provided, the completion streams — the resolved
    client must satisfy :class:`~rath.llm.StreamingChatClient`. Each
    :class:`RathLLMStreamDelta` is forwarded to ``on_event``.

    When ``persist`` is true or ``persist_path`` is given, the single output
    row is written to ``.openrath/sessions/<out.id>.jsonl`` (or to
    ``persist_path``) with a trailer.
    """

    # Concurrency invariant 7: auto-join lazy inputs before reading their
    # chunk_table.
    if user_session._pending is not None:
        user_session.synchronize()
    if agent_session._pending is not None:
        agent_session.synchronize()

    executor = resolve_executor(
        agent_provider=agent_provider, executor=executor, on_event=on_event
    )

    instruction = (
        compress_instruction.strip()
        if compress_instruction is not None
        else _DEFAULT_COMPRESS_INSTRUCTION
    )

    head = chunk_table_to_messages(agent_session.chunk_table)
    tail = chunk_table_to_messages(user_session.chunk_table)
    # P2-fix: single unpack instead of two tuple concats.
    messages: tuple[RathLLMMessage, ...] = (
        *head,
        *tail,
        RathLLMMessage(role="user", content=instruction),
    )

    prefs = replace(agent_provider, tool_choice=None)
    req = provider_into_chat_request(
        messages,
        None,
        prefs,
        default_tool_choice="none",
    )

    resp = executor.complete(req)
    body = _completion_body(resp)
    if body is None or not str(body).strip():
        raise RuntimeError("run_session_compress: empty model content")

    rows = (user_text_chunk(str(body).strip()),)
    out = Session(
        chunk_table=ChunkTable(rows=rows),
        sandbox_backend=user_session.sandbox_backend,
        _sandbox_open_spec=user_session._sandbox_open_spec,
        lineage=SessionLineage(
            producer_user_session_id=user_session.id,
            producer_system_session_id=agent_session.id,
            operator="run_session_compress",
        ),
        cumulative_usage=add_usage(None, resp.usage),
    )
    if user_session.sandbox is not None and not user_session.sandbox.closed:
        out.bind_sandbox(user_session.sandbox)

    LineageRecorder.stamp_new_session(
        out,
        parent_session_ids=(user_session.id, agent_session.id),
        lineage_operator="run_session_compress",
        lineage_kind=LineageKind.OP_SESSION_COMPRESS,
        lineage_extras=(
            ("compression.lossy", True),
            ("compression.rows_out", len(rows)),
        ),
    )

    if register_sessions:
        reg = session_registry()
        reg.register(user_session)
        reg.register(agent_session)
        reg.register(out)
        reg.set_active(out)

    if persist or persist_path is not None:
        with SessionWriter(
            out,
            sandbox_handle_id=sandbox_handle_id,
            path=persist_path,
        ) as writer:
            writer.write_chunk(0, rows[0])

    return out


def _completion_body(resp: RathLLMChatResponse) -> str | None:
    choice = resp.primary_choice
    msg = choice.message
    tcalls = msg.tool_calls
    if tcalls:
        raise RuntimeError(
            "run_session_compress: model returned tool calls but tools are disabled"
        )
    fr = choice.finish_reason
    if fr not in ("stop", "length", "content_filter"):
        raise RuntimeError(f"run_session_compress: unexpected finish_reason={fr!r}")
    content = msg.content
    return None if content is None else str(content)


__all__ = ["run_session_compress"]
