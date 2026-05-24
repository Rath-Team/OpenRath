"""Adapter: wrap a user-supplied synchronous ``ChatClient`` into an async one.

The public :class:`~rath.llm.base.ChatClient` Protocol is intentionally
synchronous so users never have to touch ``async def`` / ``await`` to plug
their own LLM provider into OpenRath. Inside the runtime, however, the
session loop awaits ``acomplete`` / ``acomplete_stream`` so multiple
sessions can share one loop.

:func:`wrap_sync_chat_client` bridges the two: it returns an
:class:`AsyncChatClientLike` that defers each call to a worker thread via
:func:`asyncio.to_thread`. Streaming is handled by iterating the sync
iterator on the worker thread and bouncing each delta back to the loop via
an :class:`asyncio.Queue`.

This module is private (``rath._async``) — users never import it directly.
The runtime calls :func:`wrap_sync_chat_client` automatically when an
adapter does not provide native ``acomplete`` / ``acomplete_stream``.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Iterator, Protocol, runtime_checkable

from rath.llm.base import ChatClient, StreamingChatClient
from rath.llm.chat_request import RathLLMChatRequest
from rath.llm.chat_response import RathLLMChatResponse, RathLLMStreamDelta
from rath.llm.provider import Provider

__all__ = [
    "AsyncChatClientLike",
    "wrap_sync_chat_client",
    "ensure_async_chat_client",
]


@runtime_checkable
class AsyncChatClientLike(Protocol):
    """Runtime-internal async chat client surface.

    Any object exposing :meth:`acomplete` is usable; :meth:`acomplete_stream`
    is optional and the runtime falls back to non-streaming when absent.
    """

    @property
    def provider(self) -> Provider: ...

    async def acomplete(self, req: RathLLMChatRequest) -> RathLLMChatResponse: ...


class _SyncChatClientAsyncWrapper:
    """``AsyncChatClientLike`` facade over a synchronous :class:`ChatClient`."""

    __slots__ = ("_sync",)

    def __init__(self, sync: ChatClient) -> None:
        self._sync = sync

    @property
    def provider(self) -> Provider:
        return self._sync.provider

    async def acomplete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
        return await asyncio.to_thread(self._sync.complete, req)

    async def acomplete_stream(
        self, req: RathLLMChatRequest
    ) -> AsyncIterator[RathLLMStreamDelta]:
        """Bridge a sync ``Iterator[RathLLMStreamDelta]`` to an async iterator.

        Raises ``TypeError`` if the underlying client does not implement
        ``complete_stream``. The runtime checks ``StreamingChatClient`` before
        calling this method, so the error is defensive.
        """
        if not isinstance(self._sync, StreamingChatClient):
            raise TypeError(
                f"{type(self._sync).__name__} does not implement complete_stream; "
                "the runtime should not have called acomplete_stream"
            )
        streaming_sync: StreamingChatClient = self._sync
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=64)
        sentinel = object()
        loop = asyncio.get_running_loop()

        def _drain() -> None:
            try:
                it: Iterator[RathLLMStreamDelta] = streaming_sync.complete_stream(req)
                for delta in it:
                    asyncio.run_coroutine_threadsafe(queue.put(delta), loop).result()
            except BaseException as exc:
                asyncio.run_coroutine_threadsafe(queue.put(exc), loop).result()
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(sentinel), loop).result()

        task = asyncio.create_task(asyncio.to_thread(_drain))
        try:
            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            # Drain task is bounded by the sync iterator; ensure it terminates
            # so the worker thread releases.
            if not task.done():
                await task


def wrap_sync_chat_client(client: ChatClient) -> AsyncChatClientLike:
    """Return an async facade over a sync ``ChatClient``.

    Users continue to write synchronous adapters that implement
    :class:`~rath.llm.base.ChatClient`. Inside the runtime, blocking
    ``complete`` calls are dispatched via :func:`asyncio.to_thread`, so
    multiple sessions running on the shared loop overlap their LLM I/O.
    """
    return _SyncChatClientAsyncWrapper(client)


def ensure_async_chat_client(client: Any) -> AsyncChatClientLike:
    """Return ``client`` unchanged if it already exposes ``acomplete``; else wrap.

    Lets the session loop accept either OpenRath's native async clients
    (``rath._async.aopenai.RathOpenAIAsyncChatClient`` etc.) or any user-supplied
    synchronous :class:`~rath.llm.base.ChatClient`.
    """
    if isinstance(client, AsyncChatClientLike):
        return client
    if isinstance(client, ChatClient):
        return wrap_sync_chat_client(client)
    raise TypeError(
        f"{type(client).__name__} is neither an AsyncChatClientLike nor a "
        f"ChatClient; cannot be used as an LLM executor"
    )
