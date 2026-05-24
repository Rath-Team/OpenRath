"""Synchronous OpenAI-compatible embedding client (thin SDK wrapper).

Mirrors :class:`rath.llm.openai.client.RathOpenAIChatClient` in style:

* :class:`EmbeddingProvider` carries credentials + model + optional output
  dimension; the only required field is ``model`` (the OpenAI SDK refuses
  to pick one for you).
* :class:`RathOpenAIEmbeddingClient` wraps ``openai.OpenAI().embeddings``.
* Credential resolution: ``EmbeddingProvider.api_key`` →
  ``OPENAI_API_KEY`` env → ``llm.embedding_provider`` config entry →
  ``llm.default_provider`` config entry.

When the ``Provider`` (chat) and ``EmbeddingProvider`` share credentials,
:meth:`EmbeddingProvider.from_config` is the recommended constructor — it
reads both ``llm.embedding_provider`` (preferred) and ``llm.default_provider``
from ``~/.openrath/config.json`` and falls back gracefully.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Sequence

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

from rath.llm.credentials import resolve_credential
from rath.llm.retry import retry_with_backoff

if TYPE_CHECKING:
    from rath.config.store import ConfigStore

__all__ = [
    "EmbeddingProvider",
    "RathOpenAIEmbeddingClient",
    "DEFAULT_EMBEDDING_MODEL",
]


#: Default model used by :meth:`EmbeddingProvider.from_config` when the
#: looked-up provider entry has no ``model`` set. Picked to match the
#: open-source default rather than a vendor-specific id.
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


_EMBEDDING_RETRYABLE: tuple[type[BaseException], ...] = (
    RateLimitError,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
)


@dataclass(frozen=True, kw_only=True, slots=True)
class EmbeddingProvider:
    """Routing + credentials for an OpenAI-compatible embeddings endpoint.

    The chat ``Provider`` (in :mod:`rath.llm.provider`) is intentionally
    *not* reused: embedding endpoints frequently live under a different
    base_url / model namespace even when the api_key is shared.
    """

    model: str
    base_url: str | None = None
    api_key: str | None = None
    #: When set, request a truncated/projected embedding vector. The OpenAI
    #: SDK passes this as ``dimensions=``. ``None`` means use the model's
    #: native dimension.
    dimensions: int | None = None
    #: Same retry knobs as :class:`Provider`; ``None`` uses built-in defaults.
    retry_max_attempts: int | None = None
    retry_base_seconds: float | None = None

    def __str__(self) -> str:
        return self.model

    def __repr__(self) -> str:
        return self.__str__()

    @classmethod
    def from_config(
        cls,
        name: str | None = None,
        *,
        store: "ConfigStore | None" = None,
        **overrides: Any,
    ) -> "EmbeddingProvider":
        """Build an :class:`EmbeddingProvider` from ``~/.openrath/config.json``.

        Lookup order:

        1. ``name`` if given.
        2. ``llm.embedding_provider`` if set.
        3. ``llm.default_provider`` (chat fallback) — uses its credentials
           but replaces ``model`` with :data:`DEFAULT_EMBEDDING_MODEL`
           since the chat model is unsuitable for embeddings.

        Raises :class:`KeyError` only when ``name`` is given explicitly and
        the entry is missing.
        """
        from rath.config.store import ConfigStore  # local — see Provider.from_config

        s = store or ConfigStore.load()
        entry = None
        use_default_fallback = False
        if name is not None:
            entry = s.get_llm_provider(name)
        else:
            embed_name = getattr(s.config.llm, "embedding_provider", None)
            if embed_name is not None and embed_name in s.config.llm.providers:
                entry = s.config.llm.providers[embed_name]
            elif s.config.llm.default_provider is not None:
                entry = s.config.llm.providers.get(s.config.llm.default_provider)
                use_default_fallback = True

        if entry is None:
            base = cls(model=DEFAULT_EMBEDDING_MODEL)
        else:
            model = entry.model
            if use_default_fallback or not model:
                model = DEFAULT_EMBEDDING_MODEL
            base = cls(
                model=model,
                api_key=entry.api_key,
                base_url=entry.base_url,
            )

        if not overrides:
            return base
        return replace(base, **overrides)


def _resolve_api_key(provider: EmbeddingProvider) -> str:
    return resolve_credential(
        provider.api_key,
        os.environ.get("OPENAI_API_KEY"),
    )


def _resolve_base_url(provider: EmbeddingProvider) -> str:
    return resolve_credential(
        provider.base_url,
        os.environ.get("OPENAI_BASE_URL"),
    )


class RathOpenAIEmbeddingClient:
    """Thin wrapper around ``openai.OpenAI().embeddings.create``.

    Construct once per :class:`EmbeddingProvider`; the underlying SDK
    client is created up-front and reused across calls.
    """

    def __init__(self, provider: EmbeddingProvider) -> None:
        key = _resolve_api_key(provider)
        if not key:
            raise ValueError(
                "No API key for EmbeddingProvider: set EmbeddingProvider.api_key, "
                "export OPENAI_API_KEY, or configure llm.embedding_provider / "
                "llm.default_provider in ~/.openrath/config.json.",
            )
        self._provider = provider
        init_kw: dict[str, Any] = {"api_key": key}
        base_url = _resolve_base_url(provider)
        if base_url:
            init_kw["base_url"] = base_url
        self._client: OpenAI = OpenAI(**init_kw)

    @property
    def provider(self) -> EmbeddingProvider:
        return self._provider

    def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        """Embed an arbitrary number of texts; returns one vector per input.

        An empty ``texts`` short-circuits to ``()`` without an API call.
        """
        if not texts:
            return ()
        kwargs: dict[str, Any] = {
            "model": self._provider.model,
            "input": list(texts),
        }
        if self._provider.dimensions is not None:
            kwargs["dimensions"] = self._provider.dimensions

        def _call() -> tuple[tuple[float, ...], ...]:
            resp = self._client.embeddings.create(**kwargs)
            return tuple(tuple(float(x) for x in d.embedding) for d in resp.data)

        return retry_with_backoff(
            _call,
            retryable=_EMBEDDING_RETRYABLE,
            max_attempts=self._provider.retry_max_attempts,
            base_seconds=self._provider.retry_base_seconds,
        )

    def embed_one(self, text: str) -> tuple[float, ...]:
        """Convenience for the single-text case."""
        vectors = self.embed((text,))
        if not vectors:
            return ()
        return vectors[0]
