"""Async session loop with resource-keyed parallel tool dispatch.

:func:`_arun_session_loop` mirrors :func:`rath.session.loop.run_session_loop`
but does its LLM completions and tool dispatch on the runtime loop, so a
single round of ``tool_calls`` can fan out in parallel when the tools touch
*different* resources.

Tool ordering within a round:

- Each call's :meth:`FlowToolCall.resource_key` produces a key tuple.
- Calls sharing one key form a queue and are awaited serially in the
  original ``tool_calls`` order — this preserves "same path → same order".
- Across distinct keys we ``asyncio.gather`` the queues so independent
  tools overlap. Non-:attr:`parallel_safe` tools default to the
  ``("global",)`` key, falling back to serial behavior identical to the
  sync loop.
- Final transcript rows are written back in the original ``tool_calls``
  order, never in completion order — so a tool that finishes earlier
  doesn't reorder the JSONL.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from rath._async.awriter import _AsyncSessionWriter
from rath._async.sync_to_async import (
    AsyncChatClientLike,
    ensure_async_chat_client,
)
from rath.flow.tool import (
    FlowToolCall,
    merge_tools_for_loop,
    tools_dict_to_schemas,
)
from rath.llm import (
    Provider,
    RathLLMChatRequest,
    RathLLMChatResponse,
    RathLLMFunctionTool,
    RathLLMMessage,
    RathLLMStreamDelta,
    chat_client_for,
)
from rath.session.chat_request_build import provider_into_chat_request
from rath.session.chunk import (
    ChunkRow,
    ChunkTable,
    assistant_turn_chunk,
    chunk_table_to_messages,
    tool_feedback_chunk,
)
from rath.session.graph import LineageKind, LineageRecorder, SessionLineage
from rath.session.loop import (
    _accumulate_stream_to_response,
    _accumulate_usage_and_check_budget,
    _loop_tool_error_payload,
    _summarize_dispatch_result,
)
from rath.session.manager import session_registry
from rath.session.session import (
    Session,
    _enter_tool_dispatch,
    _exit_tool_dispatch,
)


def _tool_body(tool: FlowToolCall, session: Session, args: Mapping[str, Any]) -> Any:
    """Run ``tool(session, args)`` with the runtime tool-dispatch flag set.

    The flag flips ``Session.chunk_table`` / ``cumulative_usage`` reads into
    "raw" mode, so a tool body inspecting its own session does not deadlock
    on the still-in-flight ``_pending`` future.
    """
    _enter_tool_dispatch()
    try:
        return tool(session, dict(args or {}))
    finally:
        _exit_tool_dispatch()


__all__ = [
    "AsyncSessionLoopExecutor",
    "_arun_session_loop",
]

logger = logging.getLogger(__name__)


@runtime_checkable
class AsyncSessionLoopExecutor(Protocol):
    """Runtime-internal counterpart of :class:`SessionLoopExecutor`."""

    async def acomplete(self, req: RathLLMChatRequest) -> RathLLMChatResponse: ...

    async def adispatch_tool(
        self,
        session: Session,
        tool: FlowToolCall,
        arguments: Mapping[str, Any],
    ) -> Any: ...

    def tool_schemas(self) -> tuple[RathLLMFunctionTool, ...]: ...


class _DefaultAsyncExecutor:
    """Wrap an :class:`AsyncChatClientLike`; dispatch sync tools via ``to_thread``."""

    __slots__ = ("_client", "_on_event")

    def __init__(
        self,
        client: AsyncChatClientLike,
        on_event: Callable[[RathLLMStreamDelta], None] | None = None,
    ) -> None:
        self._client = client
        self._on_event = on_event

    def tool_schemas(self) -> tuple[RathLLMFunctionTool, ...]:
        return ()

    async def acomplete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
        if self._on_event is None:
            return await self._client.acomplete(req)
        stream_fn = getattr(self._client, "acomplete_stream", None)
        if stream_fn is None:
            raise TypeError(
                "on_event requires an async streaming client; "
                f"{type(self._client).__name__} does not expose acomplete_stream"
            )
        # Drain the async-iter into the existing sync accumulator by buffering
        # — accumulation logic is pure and identical for sync/async deltas.
        deltas: list[RathLLMStreamDelta] = []
        on_event = self._on_event
        async for delta in stream_fn(req):
            on_event(delta)
            deltas.append(delta)
        model = getattr(getattr(self._client, "provider", None), "model", "") or ""
        return _accumulate_stream_to_response(
            iter(deltas),
            on_event=lambda _d: None,
            model=model,
        )

    async def adispatch_tool(
        self,
        session: Session,
        tool: FlowToolCall,
        arguments: Mapping[str, Any],
    ) -> Any:
        # Tools are synchronous (`FlowToolCall.__call__`); off-load to a
        # worker thread so a slow tool can't park the runtime loop.
        # ``_tool_body`` sets the re-entrancy flag so reads of
        # ``session.chunk_table`` from inside the tool see the in-flight
        # transcript without trying to synchronize() the producing future.
        return await asyncio.to_thread(_tool_body, tool, session, arguments)


class _SyncExecutorAsyncAdapter:
    """Wrap a sync :class:`SessionLoopExecutor` so the async loop can drive it.

    Sync ``complete()`` runs on the runtime loop's worker pool via
    :func:`asyncio.to_thread`; same for ``dispatch_tool``. Scripted test
    executors keep working without rewrites.
    """

    __slots__ = ("_sync",)

    def __init__(self, sync: Any) -> None:
        self._sync = sync

    def tool_schemas(self) -> tuple[RathLLMFunctionTool, ...]:
        schemas: tuple[RathLLMFunctionTool, ...] = self._sync.tool_schemas()
        return schemas

    async def acomplete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
        return await asyncio.to_thread(self._sync.complete, req)

    async def adispatch_tool(
        self,
        session: Session,
        tool: FlowToolCall,
        arguments: Mapping[str, Any],
    ) -> Any:
        sync = self._sync

        def _call() -> Any:
            _enter_tool_dispatch()
            try:
                return sync.dispatch_tool(session, tool, dict(arguments or {}))
            finally:
                _exit_tool_dispatch()

        return await asyncio.to_thread(_call)


def _resolve_async_executor(
    *,
    agent_provider: Provider,
    executor: AsyncSessionLoopExecutor | None,
    on_event: Callable[[RathLLMStreamDelta], None] | None,
) -> AsyncSessionLoopExecutor:
    if executor is not None and on_event is not None:
        raise ValueError(
            "on_event with a custom executor is not supported; "
            "wire streaming inside your executor's acomplete instead."
        )
    if executor is not None:
        # Either already an AsyncSessionLoopExecutor, or a sync one — wrap.
        if hasattr(executor, "acomplete"):
            return executor
        return _SyncExecutorAsyncAdapter(executor)
    client = ensure_async_chat_client(chat_client_for(agent_provider))
    return _DefaultAsyncExecutor(client, on_event)


async def _adispatch_round(
    out: Session,
    rows_list: list[Any],
    tool_calls: tuple[Any, ...],
    table: dict[str, FlowToolCall],
    executor: AsyncSessionLoopExecutor,
    writer: _AsyncSessionWriter | None,
) -> None:
    """Run one assistant round's ``tool_calls`` with resource-keyed parallelism.

    Bodies are awaited via ``asyncio.gather`` across distinct
    :meth:`FlowToolCall.resource_key` queues; within a queue calls run in
    the original transcript order. Results are stitched back into
    ``rows_list`` in the original ``tool_calls`` order so the persisted
    transcript stays deterministic.
    """
    n = len(tool_calls)
    bodies: list[str | None] = [None] * n
    queues: dict[tuple[str, ...], list[int]] = {}
    pre_errors: dict[int, str] = {}

    for idx, tc in enumerate(tool_calls):
        tool_name = tc.function.name
        if tc.function.arguments_parsed is None or tc.function.arguments_parse_error:
            raw_dump = tc.function.arguments or ""
            if len(raw_dump) > 2000:
                raw_dump = raw_dump[:2000] + "...(truncated)"
            pre_errors[idx] = _loop_tool_error_payload(
                "invalid_tool_arguments",
                f"tool {tool_name!r} returned non-JSON or unparseable arguments",
                detail=raw_dump,
            )
            continue
        flow_tool = table.get(tool_name)
        if flow_tool is None:
            pre_errors[idx] = _loop_tool_error_payload(
                "unknown_tool",
                f"unknown tool {tool_name!r}",
            )
            continue
        args = tc.function.arguments_parsed or {}
        try:
            key = flow_tool.resource_key(args)
        except Exception as exc:
            logger.exception(
                'resource_key() raised for tool=%s; serializing on ("global",)',
                tool_name,
            )
            pre_errors[idx] = _loop_tool_error_payload(
                "tool_execution_exception",
                f"{type(exc).__name__}: {exc}",
                detail=type(exc).__name__,
            )
            continue
        queues.setdefault(tuple(key), []).append(idx)

    for idx, body in pre_errors.items():
        bodies[idx] = body

    async def _run_queue(indices: list[int]) -> None:
        for idx in indices:
            tc = tool_calls[idx]
            tool_name = tc.function.name
            flow_tool = table[tool_name]
            try:
                raw = await executor.adispatch_tool(
                    out,
                    flow_tool,
                    tc.function.arguments_parsed or {},
                )
                bodies[idx] = _summarize_dispatch_result(flow_tool, raw)
            except Exception as exc:
                logger.exception("tool invocation failed for tool=%s", tool_name)
                bodies[idx] = _loop_tool_error_payload(
                    "tool_execution_exception",
                    f"{type(exc).__name__}: {exc}",
                    detail=type(exc).__name__,
                )

    if queues:
        await asyncio.gather(*(_run_queue(q) for q in queues.values()))

    for idx, tc in enumerate(tool_calls):
        maybe_body = bodies[idx]
        if maybe_body is None:
            # Defensive — every idx should have a body by now.
            final_body = json.dumps(
                {
                    "ok": False,
                    "error_kind": "internal_missing_result",
                    "message": "tool result missing after dispatch",
                }
            )
        else:
            final_body = maybe_body
        row = tool_feedback_chunk(tc.id, tc.function.name, final_body)
        rows_list.append(row)
        out.chunk_table = ChunkTable(rows=tuple(rows_list))
        if writer is not None:
            await writer.awrite_chunk(len(rows_list) - 1, row)


async def _arun_session_loop(
    user_session: Session,
    agent_session: Session,
    *,
    agent_provider: Provider,
    tools: list[FlowToolCall] | None = None,
    executor: AsyncSessionLoopExecutor | None = None,
    max_tool_rounds: int = 16,
    on_event: Callable[[RathLLMStreamDelta], None] | None = None,
    persist: bool = False,
    persist_path: Path | None = None,
    sandbox_handle_id: str | None = None,
    out: Session | None = None,
) -> Session:
    """Async session loop. Returns the materialized ``out`` :class:`Session`.

    This is the runtime-internal coroutine. The public sync façade
    :func:`rath.session.loop.run_session_loop` builds the ``out`` :class:`Session`
    eagerly (so callers can immediately read ``out.id``, ``out.sandbox``,
    lineage attrs), attaches a :class:`LazyValue` to ``out._pending``, and
    submits this coroutine. Reading ``out.chunk_table`` later blocks on
    ``_pending`` and publishes the final values.
    """
    table = merge_tools_for_loop(tools)
    aexec = _resolve_async_executor(
        agent_provider=agent_provider,
        executor=executor,
        on_event=on_event,
    )

    prefs = agent_provider

    # Be careful: ``user_session.chunk_table`` triggers synchronize() if the
    # input is itself a lazy session. Sync facades should join lazy inputs
    # before calling us; here we read via the property and trust the caller.
    rows_list: list[Any] = list(user_session._chunk_table.rows)
    if out is None:
        out = Session(
            chunk_table=ChunkTable(rows=tuple(rows_list)),
            sandbox_backend=user_session.sandbox_backend,
            _sandbox_open_spec=user_session._sandbox_open_spec,
            lineage=SessionLineage(
                producer_user_session_id=user_session.id,
                producer_system_session_id=agent_session.id,
            ),
        )
        if user_session.sandbox is not None and not user_session.sandbox.closed:
            out.bind_sandbox(user_session.sandbox)
        LineageRecorder.stamp_new_session(
            out,
            parent_session_ids=(user_session.id, agent_session.id),
            lineage_operator="run_session_loop",
            lineage_kind=LineageKind.OP_SESSION_LOOP,
        )
    else:
        # Sync facade pre-built ``out`` and pre-stamped lineage; seed the
        # staging table with the user rows.
        out._chunk_table = ChunkTable(rows=tuple(rows_list))
    reg = session_registry()
    reg.register(user_session)
    reg.register(agent_session)
    reg.register(out)
    reg.set_active(out)

    writer: _AsyncSessionWriter | None = None
    if persist or persist_path is not None:
        writer = _AsyncSessionWriter(
            out,
            sandbox_handle_id=sandbox_handle_id,
            path=persist_path,
        )
        for seed_index, seed_row in enumerate(rows_list):
            await writer.awrite_chunk(seed_index, seed_row)

    tool_schemas = aexec.tool_schemas()
    if not tool_schemas:
        tool_schemas = tools_dict_to_schemas(table)

    async def _append_row(row: ChunkRow) -> None:
        rows_list.append(row)
        out.chunk_table = ChunkTable(rows=tuple(rows_list))
        if writer is not None:
            await writer.awrite_chunk(len(rows_list) - 1, row)

    # head is immutable after session start — compute once outside the loop.
    head = chunk_table_to_messages(agent_session._chunk_table)
    # Incrementally extend tail with only new rows so we don't re-flatten
    # the whole chunk_table every round (ported from main).
    _tail_rendered_up_to = 0
    _tail_msgs: tuple[RathLLMMessage, ...] = ()

    try:
        rounds_used = 0
        finished = False
        for _ in range(max_tool_rounds):
            rounds_used += 1
            if len(rows_list) > _tail_rendered_up_to:
                new_slice = ChunkTable(rows=tuple(rows_list[_tail_rendered_up_to:]))
                _tail_msgs = _tail_msgs + chunk_table_to_messages(new_slice)
                _tail_rendered_up_to = len(rows_list)
            messages = head + _tail_msgs

            req = provider_into_chat_request(
                messages,
                tool_schemas,
                prefs,
                default_tool_choice="auto",
            )
            resp = await aexec.acomplete(req)
            _accumulate_usage_and_check_budget(out, resp, prefs)
            choice = resp.primary_choice
            msg = choice.message
            tcalls = msg.tool_calls

            if tcalls:
                await _append_row(
                    assistant_turn_chunk(tool_calls=tcalls, content=msg.content)
                )
                await _adispatch_round(out, rows_list, tcalls, table, aexec, writer)
                continue

            await _append_row(
                assistant_turn_chunk(tool_calls=None, content=msg.content)
            )
            if choice.finish_reason in ("stop", "length", "content_filter"):
                finished = True
                break

        if not finished and rounds_used >= max_tool_rounds:
            # Emit on rath.session.loop so existing test filters keep working
            # and the sync/async paths look identical from the outside.
            logging.getLogger("rath.session.loop").warning(
                "run_session_loop hit max_tool_rounds=%d without "
                "finish_reason in (stop, length, content_filter); "
                "last row may be a tool_result",
                max_tool_rounds,
            )
            out.lineage_extras = out.lineage_extras + (("loop.truncated", True),)
    except BaseException:
        if writer is not None:
            try:
                await writer.abandon()
            except BaseException:
                logger.exception("async session writer abandon failed")
        raise

    if writer is not None:
        await writer.aclose()

    out.chunk_table = ChunkTable(rows=tuple(rows_list))
    reg.set_active(out)
    return out
