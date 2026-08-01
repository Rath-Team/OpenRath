"""Milvus-backed memory adapter tests against real Milvus Lite."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("pymilvus")

from rath.memory import MemoryStore, MemoryStoreSpec
from rath.memory.adapters.milvus import MilvusMemoryBackend
from rath.memory.op_types import (
    MemoryOpFind,
    MemoryOpList,
    MemoryOpRead,
    MemoryOpSearch,
    MemoryOpTree,
    MemoryOpWrite,
)
from rath.memory.results import (
    MemoryExecutionFailure,
    MemoryFindResult,
    MemoryListResult,
    MemoryReadResult,
    MemoryWriteResult,
)


class _FakeEmbeddingProvider:
    model = "fake-embedding-3d"


class _FakeEmbedding:
    provider = _FakeEmbeddingProvider()

    def embed(
        self, texts: tuple[str, ...] | list[str]
    ) -> tuple[tuple[float, ...], ...]:
        return tuple(self.embed_one(text) for text in texts)

    def embed_one(self, text: str) -> tuple[float, ...]:
        lowered = text.lower()
        if any(token in lowered for token in ("dark", "night", "eyes", "theme")):
            return (1.0, 0.0, 0.0)
        if any(token in lowered for token in ("coffee", "espresso")):
            return (0.0, 1.0, 0.0)
        return (0.0, 0.0, 1.0)


class _FakeEmbedding2D:
    provider = _FakeEmbeddingProvider()

    def embed(
        self, texts: tuple[str, ...] | list[str]
    ) -> tuple[tuple[float, ...], ...]:
        return tuple(self.embed_one(text) for text in texts)

    def embed_one(self, text: str) -> tuple[float, ...]:
        return (1.0, 0.0)


@pytest.fixture
def backend() -> MilvusMemoryBackend:
    return MilvusMemoryBackend()


def _collection_name() -> str:
    return f"openrath_test_{uuid.uuid4().hex}"


def _store_options(tmp_path: Path, **overrides: object) -> dict[str, object]:
    options: dict[str, object] = {
        "uri": str(tmp_path / "milvus.db"),
        "collection_name": _collection_name(),
        "embedding": _FakeEmbedding(),
        "drop_on_close": True,
    }
    options.update(overrides)
    return options


@pytest.fixture
def store(backend: MilvusMemoryBackend, tmp_path: Path) -> Iterator[MemoryStore]:
    s = backend.open(MemoryStoreSpec(options=_store_options(tmp_path)))
    try:
        yield s
    finally:
        if not s.closed:
            backend.close(s)


def _write(
    backend: MilvusMemoryBackend,
    store: MemoryStore,
    uri: str,
    content: str,
) -> None:
    res = backend.dispatch(store, MemoryOpWrite(uri=uri, content=content))
    assert isinstance(res, MemoryWriteResult)


def test_write_read_list_tree_and_find(
    backend: MilvusMemoryBackend,
    store: MemoryStore,
) -> None:
    _write(
        backend,
        store,
        "memory://user/memories/preferences/dark_theme",
        "The user enables a dark colour theme for late-night coding.",
    )
    _write(
        backend,
        store,
        "memory://user/memories/preferences/coffee",
        "The user drinks espresso before standup.",
    )
    _write(
        backend,
        store,
        "memory://user/memories/notes/paris",
        "The user is travelling to Paris in April.",
    )

    read = backend.dispatch(
        store, MemoryOpRead(uri="memory://user/memories/preferences/dark_theme")
    )
    assert isinstance(read, MemoryReadResult)
    assert "late-night coding" in read.data

    listed = backend.dispatch(
        store, MemoryOpList(uri="memory://user/memories/preferences")
    )
    assert isinstance(listed, MemoryListResult)
    assert {(entry.name, entry.is_dir) for entry in listed.entries} == {
        ("coffee", False),
        ("dark_theme", False),
    }

    tree = backend.dispatch(store, MemoryOpTree(uri="memory://user/memories", depth=1))
    assert isinstance(tree, MemoryListResult)
    assert "memory://user/memories/preferences" in {entry.uri for entry in tree.entries}
    assert "memory://user/memories/preferences/dark_theme" in {
        entry.uri for entry in tree.entries
    }

    found = backend.dispatch(
        store, MemoryOpFind(query="reading code at night without burning my eyes")
    )
    assert isinstance(found, MemoryFindResult)
    assert found.hits
    assert found.hits[0].uri == "memory://user/memories/preferences/dark_theme"


def test_search_delegates_to_find_and_honors_target_uri(
    backend: MilvusMemoryBackend,
    store: MemoryStore,
) -> None:
    _write(
        backend,
        store,
        "memory://user/memories/preferences/dark_theme",
        "The user prefers dark mode at night.",
    )
    _write(
        backend,
        store,
        "memory://agent/memories/preferences/dark_theme",
        "The agent should use dark logs in diagnostics.",
    )

    res = backend.dispatch(
        store,
        MemoryOpSearch(
            query="dark mode",
            target_uri="memory://agent/memories/preferences",
            top_k=3,
        ),
    )
    assert isinstance(res, MemoryFindResult)
    assert [hit.uri for hit in res.hits] == [
        "memory://agent/memories/preferences/dark_theme"
    ]


def test_invalid_uri_and_missing_read_surface_typed_failures(
    backend: MilvusMemoryBackend,
    store: MemoryStore,
) -> None:
    invalid = backend.dispatch(
        store, MemoryOpWrite(uri="memory://bogus_scope_xyz/x", content="x")
    )
    assert isinstance(invalid, MemoryExecutionFailure)
    assert invalid.kind == "invalid_uri"

    missing = backend.dispatch(
        store, MemoryOpRead(uri="memory://user/memories/preferences/missing")
    )
    assert isinstance(missing, MemoryExecutionFailure)
    assert missing.kind == "not_found"


def test_reopens_existing_lite_collection(
    tmp_path: Path,
) -> None:
    collection = _collection_name()
    uri = str(tmp_path / "milvus.db")

    first_backend = MilvusMemoryBackend()
    first = first_backend.open(
        MemoryStoreSpec(
            options={
                "uri": uri,
                "collection_name": collection,
                "embedding": _FakeEmbedding(),
            }
        )
    )
    _write(
        first_backend,
        first,
        "memory://user/memories/preferences/persisted",
        "This memory should survive reopening the Milvus Lite file.",
    )
    first_backend.close(first)

    second_backend = MilvusMemoryBackend()
    second = second_backend.open(
        MemoryStoreSpec(
            options={
                "uri": uri,
                "collection_name": collection,
                "embedding": _FakeEmbedding(),
                "drop_on_close": True,
            }
        )
    )
    try:
        read = second_backend.dispatch(
            second, MemoryOpRead(uri="memory://user/memories/preferences/persisted")
        )
        assert isinstance(read, MemoryReadResult)
        assert "survive reopening" in read.data
    finally:
        second_backend.close(second)


def test_existing_collection_dimension_mismatch_returns_failure(
    tmp_path: Path,
) -> None:
    collection = _collection_name()
    uri = str(tmp_path / "milvus.db")

    first_backend = MilvusMemoryBackend()
    first = first_backend.open(
        MemoryStoreSpec(
            options={
                "uri": uri,
                "collection_name": collection,
                "embedding": _FakeEmbedding(),
            }
        )
    )
    _write(
        first_backend,
        first,
        "memory://user/memories/preferences/dim",
        "A three dimensional record.",
    )
    first_backend.close(first)

    second_backend = MilvusMemoryBackend()
    second = second_backend.open(
        MemoryStoreSpec(
            options={
                "uri": uri,
                "collection_name": collection,
                "embedding": _FakeEmbedding2D(),
                "drop_on_close": True,
            }
        )
    )
    try:
        res = second_backend.dispatch(
            second,
            MemoryOpWrite(
                uri="memory://user/memories/preferences/bad_dim",
                content="A two dimensional record.",
            ),
        )
        assert isinstance(res, MemoryExecutionFailure)
        assert res.kind == "internal"
        assert "dimension" in res.message
    finally:
        second_backend.close(second)


_HAS_LIVE_KEY = len(os.environ.get("OPENAI_API_KEY", "").strip()) >= 8
_live_only = pytest.mark.skipif(
    not _HAS_LIVE_KEY,
    reason="OPENAI_API_KEY not set (live embedding tests)",
)


@_live_only
@pytest.mark.live_llm
def test_live_openai_embedding_smoke(tmp_path: Path) -> None:
    from rath.llm.embedding import EmbeddingProvider, RathOpenAIEmbeddingClient

    api_key = os.environ["OPENAI_API_KEY"].strip()
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    model = os.environ.get("OPENAI_EMBEDDING_MODEL", "").strip() or None
    embedding = RathOpenAIEmbeddingClient(
        EmbeddingProvider(
            api_key=api_key,
            base_url=base_url,
            model=model or "text-embedding-3-small",
        )
    )
    backend = MilvusMemoryBackend()
    store = backend.open(
        MemoryStoreSpec(
            options=_store_options(
                tmp_path,
                embedding=embedding,
                collection_name=_collection_name(),
                drop_on_close=True,
            )
        )
    )
    try:
        first = backend.dispatch(
            store,
            MemoryOpWrite(
                uri="memory://user/memories/preferences/milvus",
                content="Milvus stores vector embeddings for scalable semantic retrieval.",
            ),
        )
        if isinstance(first, MemoryExecutionFailure) and first.kind == "transport":
            pytest.skip(f"live embedding endpoint unavailable: {first.detail}")
        assert isinstance(first, MemoryWriteResult)

        second = backend.dispatch(
            store,
            MemoryOpWrite(
                uri="memory://user/memories/preferences/tea",
                content="The user drinks jasmine tea on Friday afternoons.",
            ),
        )
        if isinstance(second, MemoryExecutionFailure) and second.kind == "transport":
            pytest.skip(f"live embedding endpoint unavailable: {second.detail}")
        assert isinstance(second, MemoryWriteResult)

        res = backend.dispatch(
            store,
            MemoryOpFind(
                query="Milvus vector embeddings for semantic retrieval",
                top_k=1,
            ),
        )
        if isinstance(res, MemoryExecutionFailure) and res.kind == "transport":
            pytest.skip(f"live embedding endpoint unavailable: {res.detail}")
        assert isinstance(res, MemoryFindResult)
        assert res.hits[0].uri == "memory://user/memories/preferences/milvus"
    finally:
        backend.close(store)
