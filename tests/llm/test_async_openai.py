"""Live OpenAI async-client tests — real network, no mocks.

Validates :class:`rath._async.aopenai.RathOpenAIAsyncChatClient` against the
real OpenAI API (or any OpenAI-compatible endpoint configured via
``OPENAI_API_KEY`` / ``OPENAI_BASE_URL`` / ``OPENAI_DEFAULT_MODEL``):

- One ``acomplete`` produces the same response shape as the sync client.
- Concurrent ``acomplete`` calls on the runtime loop overlap their network
  latency rather than serialising.
- ``acomplete_stream`` produces deltas and a usable final ``finish_reason``.

Gated by ``live_llm`` marker + ``OPENAI_API_KEY`` length, per
``[[feedback-testing-realonly]]``.
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest

from rath._async.aopenai import RathOpenAIAsyncChatClient
from rath._async.runtime import runtime
from rath.llm import RathLLMChatRequest, RathLLMMessage
from tests.openai_env_provider import live_openai_provider

pytestmark = [
    pytest.mark.live_llm,
    pytest.mark.skipif(
        len(os.environ.get("OPENAI_API_KEY", "").strip()) < 8,
        reason="OPENAI_API_KEY not set or too short (live API tests)",
    ),
]


@pytest.fixture
def async_client() -> RathOpenAIAsyncChatClient:
    return RathOpenAIAsyncChatClient(live_openai_provider())


def test_acomplete_ping_hits_remote_model(
    async_client: RathOpenAIAsyncChatClient,
) -> None:
    req = RathLLMChatRequest(
        messages=(
            RathLLMMessage(
                role="user",
                content="Reply with exactly the single word: pong",
            ),
        ),
        model=async_client.provider.model,
    )
    rt = runtime()
    resp = rt.run(async_client.acomplete(req))
    assert resp.id, "remote completions must return an id"
    assert resp.model
    text = (resp.primary_choice.message.content or "").strip().lower()
    assert "pong" in text
    assert resp.usage is not None
    assert resp.usage.total_tokens > 0


def test_acomplete_concurrent_calls_overlap_network_latency(
    async_client: RathOpenAIAsyncChatClient,
) -> None:
    """N parallel ``acomplete`` calls share one loop; total < N × single latency."""
    rt = runtime()
    req = RathLLMChatRequest(
        messages=(RathLLMMessage(role="user", content="Say ok."),),
        model=async_client.provider.model,
    )

    # Warm-up to measure per-call latency.
    t0 = time.perf_counter()
    rt.run(async_client.acomplete(req))
    per_call = time.perf_counter() - t0

    n = 4

    async def fanout() -> list:
        return await asyncio.gather(*(async_client.acomplete(req) for _ in range(n)))

    start = time.perf_counter()
    results = rt.run(fanout())
    elapsed = time.perf_counter() - start

    assert len(results) == n
    assert all(r.id for r in results)
    # Overlap test: parallel must beat strict serial by a comfortable margin.
    # Generous bound — networks are noisy.
    assert elapsed < per_call * n * 0.75, (
        f"async concurrency did not overlap network: per-call ≈ {per_call:.2f}s, "
        f"{n} parallel took {elapsed:.2f}s"
    )


def test_acomplete_stream_yields_deltas(
    async_client: RathOpenAIAsyncChatClient,
) -> None:
    req = RathLLMChatRequest(
        messages=(
            RathLLMMessage(
                role="user", content="Count from one to three, one number per line."
            ),
        ),
        model=async_client.provider.model,
    )
    rt = runtime()

    async def drain() -> tuple[str, str | None]:
        text = ""
        finish: str | None = None
        async for delta in async_client.acomplete_stream(req):
            if delta.content_delta:
                text += delta.content_delta
            if delta.finish_reason is not None:
                finish = delta.finish_reason
        return text, finish

    text, finish = rt.run(drain())
    assert finish == "stop"
    assert any(d.isdigit() for d in text), (
        f"expected digits in streamed text, got {text!r}"
    )
