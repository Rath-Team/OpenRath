"""Embedding-backed Find tests for :class:`LocalMemoryBackend`.

Real GLM embedding calls via :class:`RathOpenAIEmbeddingClient`. Gated by
``OPENAI_API_KEY`` (the project ``.env`` ships one for GLM); skip cleanly
when no key is configured.
"""

from __future__ import annotations

import os
from typing import Iterator

import pytest

from rath.llm.embedding import EmbeddingProvider, RathOpenAIEmbeddingClient
from rath.memory import MemoryStore, MemoryStoreSpec
from rath.memory.adapters.local import LocalMemoryBackend
from rath.memory.op_types import MemoryOpFind, MemoryOpWrite
from rath.memory.results import MemoryFindResult

_HAS_LIVE_KEY = len(os.environ.get("OPENAI_API_KEY", "").strip()) >= 8
_live_only = pytest.mark.skipif(
    not _HAS_LIVE_KEY,
    reason="OPENAI_API_KEY not set (live embedding tests)",
)


@pytest.fixture
def embedding_client() -> RathOpenAIEmbeddingClient:
    api_key = os.environ["OPENAI_API_KEY"].strip()
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    model = os.environ.get("OPENAI_EMBEDDING_MODEL", "").strip() or "embedding-3"
    return RathOpenAIEmbeddingClient(
        EmbeddingProvider(api_key=api_key, base_url=base_url, model=model),
    )


@pytest.fixture
def embed_store(
    backend: LocalMemoryBackend,
    embedding_client: RathOpenAIEmbeddingClient,
) -> Iterator[MemoryStore]:
    spec = MemoryStoreSpec(options={"embedding": embedding_client})
    s = backend.open(spec)
    try:
        yield s
    finally:
        if not s.closed:
            backend.close(s)


@_live_only
@pytest.mark.live_llm
def test_embedding_find_ranks_semantically_nearest_first(
    backend: LocalMemoryBackend, embed_store: MemoryStore
) -> None:
    """A semantically related query must outrank the lexical-only match."""
    # Three memos. The query mentions night-time reading, which semantically
    # ties to "dark mode" without sharing keywords with the others.
    backend.dispatch(
        embed_store,
        MemoryOpWrite(
            uri="viking://user/memories/preferences/dark_theme",
            content="The user enables a dark colour theme so screens are easy on the eyes after sunset.",
        ),
    )
    backend.dispatch(
        embed_store,
        MemoryOpWrite(
            uri="viking://user/memories/preferences/coffee",
            content="The user drinks espresso every morning before standup.",
        ),
    )
    backend.dispatch(
        embed_store,
        MemoryOpWrite(
            uri="viking://user/memories/notes/paris",
            content="In April the user is travelling to Paris for a weekend trip.",
        ),
    )

    res = backend.dispatch(
        embed_store,
        MemoryOpFind(query="reading code at night without burning my eyes", top_k=3),
    )
    assert isinstance(res, MemoryFindResult)
    assert len(res.hits) >= 1
    assert res.hits[0].uri == "viking://user/memories/preferences/dark_theme"


@_live_only
@pytest.mark.live_llm
def test_embedding_find_persists_vec_sidecar(
    backend: LocalMemoryBackend, embed_store: MemoryStore
) -> None:
    from pathlib import Path

    uri = "viking://user/memories/preferences/persisted"
    backend.dispatch(
        embed_store,
        MemoryOpWrite(uri=uri, content="A short body that gets embedded."),
    )
    # Trigger a Find to force sidecar creation.
    backend.dispatch(embed_store, MemoryOpFind(query="body"))
    sidecar = (
        Path(embed_store.handle) / "user" / "memories" / "preferences" / "persisted.vec"
    )
    assert sidecar.is_file(), "first Find must persist a .vec sidecar"
    payload = sidecar.read_text(encoding="utf-8")
    assert '"vector"' in payload
    assert '"model"' in payload


@_live_only
@pytest.mark.live_llm
def test_embedding_find_reuses_cached_sidecar(
    backend: LocalMemoryBackend, embed_store: MemoryStore
) -> None:
    """Second call must not rewrite the sidecar (mtime stays put)."""
    from pathlib import Path

    uri = "viking://user/memories/preferences/cached"
    backend.dispatch(
        embed_store,
        MemoryOpWrite(uri=uri, content="Body that survives a second query."),
    )
    sidecar = (
        Path(embed_store.handle) / "user" / "memories" / "preferences" / "cached.vec"
    )

    backend.dispatch(embed_store, MemoryOpFind(query="something"))
    assert sidecar.is_file()
    first_mtime = sidecar.stat().st_mtime_ns

    backend.dispatch(embed_store, MemoryOpFind(query="something else entirely"))
    second_mtime = sidecar.stat().st_mtime_ns
    assert first_mtime == second_mtime, "cached vec must not be rewritten"
