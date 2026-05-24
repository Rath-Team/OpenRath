"""Async Anthropic chat client (private; runtime-internal).

Mirrors :class:`rath.llm.anthropic.client.RathAnthropicChatClient` but uses
``anthropic.AsyncAnthropic`` so completions ``await`` directly on
:class:`rath._async.runtime.OpenRathRuntime`'s loop.

Pure helpers (``build_anthropic_kwargs``, ``normalize_anthropic_response``)
are reused from the sync client.
"""

from __future__ import annotations

import os
from typing import Any

from anthropic import AsyncAnthropic

from rath._async.aretry import aretry_with_backoff
from rath.llm.anthropic.client import (
    ANTHROPIC_RETRYABLE,
    _config_provider_entry,
)
from rath.llm.anthropic.create_kwargs import build_anthropic_kwargs
from rath.llm.anthropic.normalize import normalize_anthropic_response
from rath.llm.chat_request import RathLLMChatRequest
from rath.llm.chat_response import RathLLMChatResponse
from rath.llm.credentials import resolve_credential
from rath.llm.provider import Provider

__all__ = ["RathAnthropicAsyncChatClient"]


class RathAnthropicAsyncChatClient:
    """Async client around ``anthropic.AsyncAnthropic().messages.create``."""

    def __init__(self, provider: Provider) -> None:
        entry = _config_provider_entry() if not provider.api_key else None
        key = resolve_credential(
            provider.api_key,
            os.environ.get("ANTHROPIC_API_KEY"),
            getattr(entry, "api_key", None),
        )
        if not key:
            raise ValueError(
                "No Anthropic api_key found: Provider.api_key is empty, "
                "ANTHROPIC_API_KEY is not set in the environment, and no "
                "llm.default_provider with an api_key is configured."
            )
        self._provider = provider
        init_kw: dict[str, Any] = {"api_key": key}
        bu = resolve_credential(
            provider.base_url,
            os.environ.get("ANTHROPIC_BASE_URL"),
            getattr(entry, "base_url", None),
        )
        if bu:
            init_kw["base_url"] = bu
        self._client = AsyncAnthropic(**init_kw)

    @property
    def provider(self) -> Provider:
        return self._provider

    async def acomplete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
        """Run ``messages.create`` (async) and normalize the response."""
        default_model = (
            self._provider.model
            or os.environ.get("ANTHROPIC_DEFAULT_MODEL")
            or getattr(_config_provider_entry(), "model", None)
        )
        kwargs = build_anthropic_kwargs(req, default_model=default_model)

        async def _call() -> RathLLMChatResponse:
            message = await self._client.messages.create(**kwargs)
            payload = message.model_dump(mode="json")
            return normalize_anthropic_response(payload)

        return await aretry_with_backoff(
            _call,
            retryable=ANTHROPIC_RETRYABLE,
            max_attempts=self._provider.retry_max_attempts,
            base_seconds=self._provider.retry_base_seconds,
        )
