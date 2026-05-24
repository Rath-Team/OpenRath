"""Synchronous Anthropic chat client (thin SDK wrapper).

Mirrors :class:`~rath.llm.openai.client.RathOpenAIChatClient`: same Protocol,
same retry behavior, same Provider fields. Translation between OpenRath's
request / response dataclasses and the Anthropic messages API happens in
:mod:`rath.llm.anthropic.create_kwargs` and :mod:`rath.llm.anthropic.normalize`
(pure functions, fixture-testable).

Empty :attr:`Provider.api_key` falls back to ``ANTHROPIC_API_KEY``; empty
``base_url`` falls back to ``ANTHROPIC_BASE_URL``.
"""

from __future__ import annotations

import os
from typing import Any

from anthropic import (
    Anthropic,
)
from anthropic import (
    APIConnectionError as _AnthropicAPIConnectionError,
)
from anthropic import (
    APITimeoutError as _AnthropicAPITimeoutError,
)
from anthropic import (
    InternalServerError as _AnthropicInternalServerError,
)
from anthropic import (
    RateLimitError as _AnthropicRateLimitError,
)

from rath.llm.anthropic.create_kwargs import build_anthropic_kwargs
from rath.llm.anthropic.normalize import normalize_anthropic_response
from rath.llm.chat_request import RathLLMChatRequest
from rath.llm.chat_response import RathLLMChatResponse
from rath.llm.credentials import resolve_credential
from rath.llm.provider import Provider
from rath.llm.retry import retry_with_backoff

#: Anthropic's transient exception classes — the default ``retryable=`` tuple
#: passed by :class:`RathAnthropicChatClient`. Exported for symmetry with
#: :data:`rath.llm.openai.OPENAI_RETRYABLE`.
#: Anthropic's transient exception classes — the default ``retryable=`` tuple
#: passed by :class:`RathAnthropicChatClient`. Exported for symmetry with
#: :data:`rath.llm.openai.OPENAI_RETRYABLE`.
ANTHROPIC_RETRYABLE: tuple[type[BaseException], ...] = (
    _AnthropicRateLimitError,
    _AnthropicAPIConnectionError,
    _AnthropicAPITimeoutError,
    _AnthropicInternalServerError,
)


__all__ = ["RathAnthropicChatClient", "ANTHROPIC_RETRYABLE"]


def _config_provider_entry() -> Any:
    """Load the first Anthropic-kind provider entry from the config file.

    Returns ``None`` if the config file is absent, malformed, or has no
    ``provider_kind="anthropic"`` entry. Errors are swallowed by design —
    config is a fallback below explicit kwargs and env vars.

    Since :meth:`ConfigStore.load` now caches by mtime, repeated calls are
    effectively free (no disk re-read unless the file was modified).
    """
    try:
        from rath.config.store import ConfigStore

        return ConfigStore.load().find_provider_by_kind("anthropic")
    except (FileNotFoundError, RuntimeError):
        return None


class RathAnthropicChatClient:
    """Thin client around ``anthropic.Anthropic().messages.create`` (non-streaming)."""

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
                "llm.default_provider with an api_key is configured in "
                "~/.openrath/config.json. Pass api_key= to Provider(...), "
                "export ANTHROPIC_API_KEY, or run Provider.from_config(...).",
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
        self._client = Anthropic(**init_kw)

    @property
    def provider(self) -> Provider:
        return self._provider

    def complete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
        """Run ``messages.create`` and normalize the response.

        Transient errors are retried per :attr:`Provider.retry_max_attempts` /
        :attr:`Provider.retry_base_seconds`. The retryable set is the
        Anthropic-flavored quadruple (``RateLimitError``, ``APIConnectionError``,
        ``APITimeoutError``, ``InternalServerError``).
        """
        default_model = (
            self._provider.model
            or os.environ.get("ANTHROPIC_DEFAULT_MODEL")
            or getattr(_config_provider_entry(), "model", None)
        )
        kwargs = build_anthropic_kwargs(req, default_model=default_model)

        def _call() -> RathLLMChatResponse:
            message = self._client.messages.create(**kwargs)
            payload = message.model_dump(mode="json")
            return normalize_anthropic_response(payload)

        return retry_with_backoff(
            _call,
            retryable=ANTHROPIC_RETRYABLE,
            max_attempts=self._provider.retry_max_attempts,
            base_seconds=self._provider.retry_base_seconds,
        )
