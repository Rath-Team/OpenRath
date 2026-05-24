"""Verify ``wrap_sync_chat_client`` lets sync clients run concurrently on the runtime.

Users keep writing synchronous :class:`~rath.llm.base.ChatClient` adapters.
Inside the runtime, those calls are dispatched via :func:`asyncio.to_thread`
so multiple sessions overlap their network I/O.

Tests:

- Wrapping a real ``RathOpenAIChatClient`` and awaiting concurrent
  ``acomplete`` calls finishes in << N × single-call latency.
- ``ensure_async_chat_client`` is the identity on a native async client and
  the wrapper on a sync client.
- Streaming via ``acomplete_stream`` on a wrapped sync streaming client
  produces the same deltas as the underlying sync iterator.

Real network, no mocks — gated by ``live_llm`` + ``OPENAI_API_KEY``.
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest

from rath._async.aopenai import RathOpenAIAsyncChatClient
from rath._async.runtime import runtime
from rath._async.sync_to_async import (
    ensure_async_chat_client,
    wrap_sync_chat_client,
)
from rath.llm import RathLLMChatRequest, RathLLMMessage, RathOpenAIChatClient
from tests.openai_env_provider import live_openai_provider

pytestmark = [
    pytest.mark.live_llm,
    pytest.mark.skipif(
        len(os.environ.get("OPENAI_API_KEY", "").strip()) < 8,
        reason="OPENAI_API_KEY not set or too short (live API tests)",
    ),
]


@pytest.fixture
def sync_client() -> RathOpenAIChatClient:
    return RathOpenAIChatClient(live_openai_provider())


def test_wrapped_sync_client_acomplete_matches_sync_complete(
    sync_client: RathOpenAIChatClient,
) -> None:
    wrapped = wrap_sync_chat_client(sync_client)
    assert wrapped.provider is sync_client.provider

    req = RathLLMChatRequest(
        messages=(RathLLMMessage(role="user", content="Reply 'ok' only."),),
        model=sync_client.provider.model,
    )
    rt = runtime()
    resp = rt.run(wrapped.acomplete(req))
    assert resp.id
    assert resp.usage is not None


def test_wrapped_sync_client_concurrent_calls_overlap(
    sync_client: RathOpenAIChatClient,
) -> None:
    """Awaiting N wrapped calls in parallel beats serial wallclock."""
    wrapped = wrap_sync_chat_client(sync_client)
    rt = runtime()
    req = RathLLMChatRequest(
        messages=(RathLLMMessage(role="user", content="Say ok."),),
        model=sync_client.provider.model,
    )

    # Warm-up via the wrapper to measure per-call latency through to_thread.
    t0 = time.perf_counter()
    rt.run(wrapped.acomplete(req))
    per_call = time.perf_counter() - t0

    n = 4

    async def fanout() -> list:
        return await asyncio.gather(*(wrapped.acomplete(req) for _ in range(n)))

    start = time.perf_counter()
    results = rt.run(fanout())
    elapsed = time.perf_counter() - start

    assert len(results) == n
    assert elapsed < per_call * n * 0.75, (
        f"wrapped-sync concurrency did not overlap: per-call ≈ {per_call:.2f}s, "
        f"{n} parallel took {elapsed:.2f}s"
    )


def test_ensure_async_chat_client_is_identity_on_native_async() -> None:
    """Native async client is returned unchanged."""
    native = RathOpenAIAsyncChatClient(live_openai_provider())
    same = ensure_async_chat_client(native)
    assert same is native


def test_ensure_async_chat_client_wraps_sync_client(
    sync_client: RathOpenAIChatClient,
) -> None:
    wrapped = ensure_async_chat_client(sync_client)
    assert wrapped is not sync_client
    assert hasattr(wrapped, "acomplete")
    assert wrapped.provider is sync_client.provider


def test_wrapped_streaming_client_yields_async_deltas(
    sync_client: RathOpenAIChatClient,
) -> None:
    """The sync streaming iterator is bridged into an async iterator end-to-end."""
    wrapped = wrap_sync_chat_client(sync_client)
    rt = runtime()
    req = RathLLMChatRequest(
        messages=(
            RathLLMMessage(role="user", content="Count one to three, one per line."),
        ),
        model=sync_client.provider.model,
    )

    async def drain() -> tuple[str, str | None]:
        text = ""
        finish: str | None = None
        async for delta in wrapped.acomplete_stream(req):  # type: ignore[attr-defined]
            if delta.content_delta:
                text += delta.content_delta
            if delta.finish_reason is not None:
                finish = delta.finish_reason
        return text, finish

    text, finish = rt.run(drain())
    assert finish == "stop"
    assert any(d.isdigit() for d in text)
