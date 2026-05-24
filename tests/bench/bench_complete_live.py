"""Live LLM completion micro-benchmark — gated by ``live_llm`` marker.

Measures the *scheduling* overhead OpenRath adds on top of a real OpenAI
``chat.completions.create`` call. The remote round-trip dominates total
wallclock; what we care about regressing here is the per-call wrapper
cost (request build, response normalisation, runtime hop).
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from rath._async.aopenai import RathOpenAIAsyncChatClient
from rath._async.runtime import runtime
from rath.llm import RathLLMChatRequest, RathLLMMessage
from tests.openai_env_provider import live_openai_provider

pytestmark = [
    pytest.mark.bench,
    pytest.mark.live_llm,
    pytest.mark.skipif(
        len(os.environ.get("OPENAI_API_KEY", "").strip()) < 8,
        reason="OPENAI_API_KEY not set",
    ),
]


@pytest.fixture(scope="module")
def _async_client() -> RathOpenAIAsyncChatClient:
    return RathOpenAIAsyncChatClient(live_openai_provider())


def test_bench_acomplete_minimal(
    benchmark: Any, _async_client: RathOpenAIAsyncChatClient
) -> None:
    """Smallest possible round-trip; measures end-to-end facade overhead."""
    req = RathLLMChatRequest(
        messages=(
            RathLLMMessage(
                role="user",
                content="Reply with exactly: ok",
            ),
        ),
        model=_async_client.provider.model,
    )
    rt = runtime()

    def _one() -> None:
        rt.run(_async_client.acomplete(req))

    benchmark.pedantic(_one, rounds=3, iterations=1, warmup_rounds=1)
