"""Integration tests for :class:`RathOpenAIEmbeddingClient` (no mocks).

Hits the live OpenAI-compatible embedding endpoint configured via
``OPENAI_API_KEY`` / ``OPENAI_BASE_URL`` / ``OPENAI_EMBEDDING_MODEL`` (or
the ``llm.embedding_provider`` entry in ``~/.openrath/config.json``).
"""

from __future__ import annotations

import math
import os

import pytest

from rath.llm import (
    EmbeddingProvider,
    RathOpenAIEmbeddingClient,
)

_HAS_LIVE_KEY = len(os.environ.get("OPENAI_API_KEY", "").strip()) >= 8
_live_only = pytest.mark.skipif(
    not _HAS_LIVE_KEY,
    reason="OPENAI_API_KEY not set or too short (live API tests)",
)


@pytest.fixture
def provider() -> EmbeddingProvider:
    api_key = os.environ["OPENAI_API_KEY"].strip()
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    model = (
        os.environ.get("OPENAI_EMBEDDING_MODEL", "").strip()
        or os.environ.get("OPENAI_DEFAULT_EMBEDDING_MODEL", "").strip()
        or "embedding-3"
    )
    return EmbeddingProvider(api_key=api_key, base_url=base_url, model=model)


@pytest.fixture
def client(provider: EmbeddingProvider) -> RathOpenAIEmbeddingClient:
    return RathOpenAIEmbeddingClient(provider)


@_live_only
@pytest.mark.live_llm
def test_embed_one_returns_a_tuple_of_floats(
    client: RathOpenAIEmbeddingClient,
) -> None:
    vec = client.embed_one("dark mode preference")
    assert isinstance(vec, tuple)
    assert len(vec) > 0
    assert all(isinstance(x, float) for x in vec)
    norm = math.sqrt(sum(x * x for x in vec))
    assert norm > 0.0  # non-degenerate vector


@_live_only
@pytest.mark.live_llm
def test_embed_batch_returns_one_vector_per_input(
    client: RathOpenAIEmbeddingClient,
) -> None:
    texts = ("hello world", "completely different content", "third one")
    vectors = client.embed(texts)
    assert isinstance(vectors, tuple)
    assert len(vectors) == 3
    dims = {len(v) for v in vectors}
    assert len(dims) == 1, f"all returned vectors must share a dimension, got {dims}"


@_live_only
@pytest.mark.live_llm
def test_embed_batch_distinguishes_dissimilar_texts(
    client: RathOpenAIEmbeddingClient,
) -> None:
    """Cosine(near) > cosine(far) for a clear semantic separation."""
    texts = (
        "I love dark mode in code editors.",
        "Set the theme to dark for better readability at night.",
        "The capital of France is Paris.",
    )
    a, b, c = client.embed(texts)

    def cos(u: tuple[float, ...], v: tuple[float, ...]) -> float:
        dot = sum(x * y for x, y in zip(u, v))
        nu = math.sqrt(sum(x * x for x in u))
        nv = math.sqrt(sum(x * x for x in v))
        return dot / (nu * nv) if nu and nv else 0.0

    near = cos(a, b)
    far = cos(a, c)
    assert near > far, (
        f"semantically near pair must outrank far pair: near={near} far={far}"
    )


@_live_only
@pytest.mark.live_llm
def test_embed_empty_batch_returns_empty_tuple(
    client: RathOpenAIEmbeddingClient,
) -> None:
    assert client.embed(()) == ()


def test_provider_from_config_uses_embedding_provider_entry(tmp_path) -> None:
    """``EmbeddingProvider.from_config`` reads ``llm.embedding_provider`` first."""
    from rath.config.schema import (
        LLMConfig,
        LLMProviderConfig,
        RathConfig,
    )
    from rath.config.store import ConfigStore

    cfg_path = tmp_path / "config.json"
    cfg = RathConfig(
        llm=LLMConfig(
            default_provider="chat",
            embedding_provider="embed",
            providers={
                "chat": LLMProviderConfig(
                    provider_kind="openai",
                    api_key="sk-chat",
                    base_url="https://chat.example/v1",
                    model="gpt-x",
                ),
                "embed": LLMProviderConfig(
                    provider_kind="openai",
                    api_key="sk-embed",
                    base_url="https://embed.example/v1",
                    model="embedding-x",
                ),
            },
        ),
    )
    store = ConfigStore(path=cfg_path)
    store._data = cfg  # bypass round-trip — we want exact in-memory state
    prov = EmbeddingProvider.from_config(store=store)
    assert prov.api_key == "sk-embed"
    assert prov.base_url == "https://embed.example/v1"
    assert prov.model == "embedding-x"


def test_provider_from_config_falls_back_to_default_when_no_embedding_entry(
    tmp_path,
) -> None:
    from rath.config.schema import (
        LLMConfig,
        LLMProviderConfig,
        RathConfig,
    )
    from rath.config.store import ConfigStore

    cfg_path = tmp_path / "config.json"
    cfg = RathConfig(
        llm=LLMConfig(
            default_provider="chat",
            providers={
                "chat": LLMProviderConfig(
                    provider_kind="openai",
                    api_key="sk-chat",
                    base_url="https://chat.example/v1",
                    model="gpt-x",
                ),
            },
        ),
    )
    store = ConfigStore(path=cfg_path)
    store._data = cfg
    prov = EmbeddingProvider.from_config(store=store)
    # falls back: shares api_key + base_url with default chat entry
    assert prov.api_key == "sk-chat"
    assert prov.base_url == "https://chat.example/v1"
    # but default-model differs (chat model is unsuitable for embeddings)
    assert prov.model and prov.model != "gpt-x"
