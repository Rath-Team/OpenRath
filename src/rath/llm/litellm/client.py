"""Synchronous LiteLLM chat client (thin wrapper around ``litellm.completion``).

LiteLLM provides a unified interface to 100+ LLM providers using the
OpenAI completion format.  Because ``litellm.completion()`` returns
OpenAI-compatible ``ModelResponse`` objects, this adapter reuses the
OpenAI normalization and kwargs-building helpers from
:mod:`rath.llm.openai`.

Empty :attr:`Provider.api_key` falls back to ``LITELLM_API_KEY``;
empty ``base_url`` falls back to ``LITELLM_API_BASE``.  When neither is
set, LiteLLM resolves credentials from provider-specific environment
variables (e.g. ``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``) internally.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from litellm import completion as litellm_completion
from litellm.exceptions import (
    APIConnectionError as _LiteLLMAPIConnectionError,
)
from litellm.exceptions import (
    InternalServerError as _LiteLLMInternalServerError,
)
from litellm.exceptions import (
    RateLimitError as _LiteLLMRateLimitError,
)
from litellm.exceptions import (
    ServiceUnavailableError as _LiteLLMServiceUnavailableError,
)
from litellm.exceptions import (
    Timeout as _LiteLLMTimeout,
)

from rath.config.env import env_value
from rath.llm.chat_request import RathLLMChatRequest
from rath.llm.chat_response import RathLLMChatResponse, RathLLMStreamDelta
from rath.llm.credentials import resolve_credential
from rath.llm.openai.client import _chunk_to_deltas
from rath.llm.openai.create_kwargs import to_create_kwargs, to_create_kwargs_stream
from rath.llm.openai.normalize import normalize_chat_completion
from rath.llm.provider import Provider
from rath.llm.retry import retry_with_backoff

LITELLM_RETRYABLE: tuple[type[BaseException], ...] = (
    _LiteLLMRateLimitError,
    _LiteLLMAPIConnectionError,
    _LiteLLMTimeout,
    _LiteLLMServiceUnavailableError,
    _LiteLLMInternalServerError,
)


def _resolve_litellm_key(provider: Provider) -> str:
    """Resolve LiteLLM ``api_key`` from Provider → env."""
    return resolve_credential(provider.api_key, env_value("LITELLM_API_KEY"))


def _resolve_litellm_base(provider: Provider) -> str:
    """Resolve LiteLLM ``api_base`` from Provider → env."""
    return resolve_credential(provider.base_url, env_value("LITELLM_API_BASE"))


__all__ = ["RathLiteLLMChatClient", "LITELLM_RETRYABLE"]


class RathLiteLLMChatClient:
    """Thin client around ``litellm.completion`` (sync + streaming).

    Model names use LiteLLM's provider-prefixed format
    (e.g. ``anthropic/claude-sonnet-4-20250514``, ``gemini/gemini-2.0-flash``,
    ``azure/gpt-4o``).  ``drop_params=True`` is always set so that
    provider-unsupported kwargs are silently dropped instead of raising.
    """

    def __init__(self, provider: Provider) -> None:
        key = _resolve_litellm_key(provider)
        self._provider = provider
        self._api_key = key or None
        bu = _resolve_litellm_base(provider)
        self._api_base = bu or None

    @property
    def provider(self) -> Provider:
        return self._provider

    def _inject_litellm_kwargs(self, kwargs: dict[str, Any]) -> None:
        """Add LiteLLM-specific kwargs (drop_params, api_key, api_base)."""
        kwargs["drop_params"] = True
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._api_base:
            kwargs["api_base"] = self._api_base

    def complete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
        """Run ``litellm.completion`` and normalize the response.

        Transient errors are retried per :attr:`Provider.retry_max_attempts` /
        :attr:`Provider.retry_base_seconds`.
        """
        default_model = self._provider.model or env_value("LITELLM_MODEL")
        kwargs = to_create_kwargs(req, default_model=default_model)
        self._inject_litellm_kwargs(kwargs)

        def _call() -> RathLLMChatResponse:
            response = litellm_completion(**kwargs)
            return normalize_chat_completion(response)

        return retry_with_backoff(
            _call,
            retryable=LITELLM_RETRYABLE,
            max_attempts=self._provider.retry_max_attempts,
            base_seconds=self._provider.retry_base_seconds,
        )

    def complete_stream(self, req: RathLLMChatRequest) -> Iterator[RathLLMStreamDelta]:
        """Yield ``RathLLMStreamDelta`` for each chunk of a streaming completion.

        Transient errors during the initial ``litellm.completion`` call are
        retried; once the iterator starts producing chunks, retries are no
        longer possible.
        """
        default_model = self._provider.model or env_value("LITELLM_MODEL")
        kwargs = to_create_kwargs_stream(req, default_model=default_model)
        self._inject_litellm_kwargs(kwargs)

        def _open_stream() -> Any:
            return litellm_completion(**kwargs)

        stream = retry_with_backoff(
            _open_stream,
            retryable=LITELLM_RETRYABLE,
            max_attempts=self._provider.retry_max_attempts,
            base_seconds=self._provider.retry_base_seconds,
        )
        for chunk in stream:
            yield from _chunk_to_deltas(chunk)
