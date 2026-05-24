"""Async OpenAI chat client (private; runtime-internal).

Mirrors :class:`rath.llm.openai.client.RathOpenAIChatClient` but uses
``openai.AsyncOpenAI`` so completions and streams ``await`` directly on
:class:`rath._async.runtime.OpenRathRuntime`'s loop. Multiple concurrent
completions therefore share one HTTP connection pool and one loop, rather
than blocking N worker threads.

Pure helpers (``to_create_kwargs``, ``normalize_chat_completion``,
``_chunk_to_deltas``) are reused as-is from the sync client.

This module is **not** part of the public API. Users continue to write and
register the synchronous :class:`~rath.llm.base.ChatClient`; the runtime
chooses between the native async client and ``wrap_sync_chat_client(...)``
internally.
"""

from __future__ import annotations

import os
from typing import Any, AsyncIterator

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncAzureOpenAI,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from rath._async.aretry import aretry_with_backoff
from rath.llm.chat_request import RathLLMChatRequest
from rath.llm.chat_response import (
    RathLLMChatResponse,
    RathLLMStreamDelta,
)
from rath.llm.credentials import resolve_credential
from rath.llm.openai.client import (
    OPENAI_RETRYABLE,
    _chunk_to_deltas,
    _config_default_model,
    _config_provider_entry,
    _is_azure_endpoint,
)
from rath.llm.openai.create_kwargs import to_create_kwargs, to_create_kwargs_stream
from rath.llm.openai.normalize import normalize_chat_completion
from rath.llm.provider import Provider

__all__ = ["RathOpenAIAsyncChatClient"]


def _resolve_base_url(provider: Provider) -> str:
    entry = _config_provider_entry() if not provider.base_url else None
    return resolve_credential(
        provider.base_url,
        os.environ.get("OPENAI_BASE_URL"),
        os.environ.get("AZURE_OPENAI_ENDPOINT"),
        getattr(entry, "base_url", None),
    )


def _resolve_api_key(provider: Provider, base_url: str) -> str:
    entry = _config_provider_entry() if not provider.api_key else None
    config_key = getattr(entry, "api_key", None)
    if _is_azure_endpoint(base_url):
        return resolve_credential(
            provider.api_key,
            os.environ.get("AZURE_OPENAI_API_KEY"),
            os.environ.get("AZURE_API_KEY"),
            os.environ.get("OPENAI_API_KEY"),
            config_key,
        )
    return resolve_credential(
        provider.api_key,
        os.environ.get("OPENAI_API_KEY"),
        os.environ.get("AZURE_OPENAI_API_KEY"),
        config_key,
    )


class RathOpenAIAsyncChatClient:
    """Async client around ``openai.AsyncOpenAI`` (chat completions + streams)."""

    def __init__(self, provider: Provider) -> None:
        base_url = _resolve_base_url(provider)
        key = _resolve_api_key(provider, base_url)
        if not key:
            raise ValueError(
                "No API key found: Provider.api_key is empty, none of "
                "OPENAI_API_KEY / AZURE_OPENAI_API_KEY / AZURE_API_KEY are "
                "set in the environment, and no llm.default_provider with an "
                "api_key is configured in ~/.openrath/config.json."
            )
        self._provider = provider
        self._client: AsyncOpenAI | AsyncAzureOpenAI

        use_azure_legacy = _is_azure_endpoint(base_url) and "/openai/v1" not in base_url
        if use_azure_legacy:
            api_version = (
                os.environ.get("OPENAI_API_VERSION")
                or os.environ.get("AZURE_OPENAI_API_VERSION")
                or "2024-10-21"
            )
            self._client = AsyncAzureOpenAI(
                api_key=key,
                azure_endpoint=base_url,
                api_version=api_version,
            )
        else:
            init_kw: dict[str, Any] = {"api_key": key}
            if base_url:
                init_kw["base_url"] = base_url
            self._client = AsyncOpenAI(**init_kw)

    @property
    def provider(self) -> Provider:
        return self._provider

    async def acomplete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
        """Run ``chat.completions.create`` (async) and normalize the response."""
        default_model = (
            self._provider.model
            or os.environ.get("OPENAI_DEFAULT_MODEL")
            or _config_default_model()
        )
        kwargs = to_create_kwargs(req, default_model=default_model)

        async def _call() -> RathLLMChatResponse:
            completion = await self._client.chat.completions.create(**kwargs)
            return normalize_chat_completion(completion)

        return await aretry_with_backoff(
            _call,
            retryable=OPENAI_RETRYABLE,
            max_attempts=self._provider.retry_max_attempts,
            base_seconds=self._provider.retry_base_seconds,
        )

    async def acomplete_stream(
        self, req: RathLLMChatRequest
    ) -> AsyncIterator[RathLLMStreamDelta]:
        """Yield ``RathLLMStreamDelta`` for each chunk of a streaming completion."""
        default_model = (
            self._provider.model
            or os.environ.get("OPENAI_DEFAULT_MODEL")
            or _config_default_model()
        )
        kwargs = to_create_kwargs_stream(req, default_model=default_model)

        async def _open_stream() -> Any:
            return await self._client.chat.completions.create(**kwargs)

        stream = await aretry_with_backoff(
            _open_stream,
            retryable=(
                RateLimitError,
                APIConnectionError,
                APITimeoutError,
                InternalServerError,
            ),
            max_attempts=self._provider.retry_max_attempts,
            base_seconds=self._provider.retry_base_seconds,
        )
        async for chunk in stream:
            for delta in _chunk_to_deltas(chunk):
                yield delta
