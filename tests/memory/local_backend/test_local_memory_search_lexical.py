"""Lexical (BM25) Find tests for :class:`LocalMemoryBackend`.

Runs without any LLM provider — exercises the degradation path where
``embedding_provider`` is unset and we fall back to a pure-stdlib BM25
ranker over the ``.md`` bodies. No mocks; real filesystem.
"""

from __future__ import annotations

from rath.memory import MemoryStore
from rath.memory.adapters.local import LocalMemoryBackend
from rath.memory.op_types import MemoryOpFind, MemoryOpWrite
from rath.memory.results import MemoryFindResult


def _seed(backend: LocalMemoryBackend, store: MemoryStore) -> None:
    backend.dispatch(
        store,
        MemoryOpWrite(
            uri="viking://user/memories/preferences/dark_mode",
            content="The user prefers dark mode in code editors at night.",
        ),
    )
    backend.dispatch(
        store,
        MemoryOpWrite(
            uri="viking://user/memories/preferences/language",
            content="The user reads English and prefers it for documentation.",
        ),
    )
    backend.dispatch(
        store,
        MemoryOpWrite(
            uri="viking://user/memories/notes/trip",
            content="In April we are going to Paris for a long weekend.",
        ),
    )


def test_find_returns_empty_on_empty_store(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    res = backend.dispatch(store, MemoryOpFind(query="anything"))
    assert isinstance(res, MemoryFindResult)
    assert res.hits == ()


def test_find_lexical_ranks_keyword_match_first(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    _seed(backend, store)
    res = backend.dispatch(store, MemoryOpFind(query="dark mode at night", top_k=3))
    assert isinstance(res, MemoryFindResult)
    assert len(res.hits) >= 1
    assert res.hits[0].uri == "viking://user/memories/preferences/dark_mode"


def test_find_respects_top_k(backend: LocalMemoryBackend, store: MemoryStore) -> None:
    _seed(backend, store)
    res = backend.dispatch(store, MemoryOpFind(query="user", top_k=2))
    assert isinstance(res, MemoryFindResult)
    assert len(res.hits) <= 2


def test_find_scopes_to_target_uri(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    _seed(backend, store)
    res = backend.dispatch(
        store,
        MemoryOpFind(
            query="user",
            target_uri="viking://user/memories/notes",
            top_k=10,
        ),
    )
    assert isinstance(res, MemoryFindResult)
    # Notes-scoped search must not bleed into preferences/.
    for hit in res.hits:
        assert hit.uri.startswith("viking://user/memories/notes/")


def test_find_snippet_is_first_chars_of_body(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    body = "Paris in springtime is overrated but the user loves it anyway."
    backend.dispatch(
        store,
        MemoryOpWrite(uri="viking://user/memories/notes/paris", content=body),
    )
    res = backend.dispatch(store, MemoryOpFind(query="Paris springtime"))
    assert isinstance(res, MemoryFindResult)
    assert res.hits, "find must return at least one hit"
    snippet = res.hits[0].snippet or ""
    assert snippet.startswith("Paris")


def test_find_returns_zero_score_when_no_term_overlap(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    _seed(backend, store)
    res = backend.dispatch(
        store, MemoryOpFind(query="zzzqqqxxx-nonexistent-word", top_k=5)
    )
    assert isinstance(res, MemoryFindResult)
    # Either no hits at all, or every hit has score 0.0.
    if res.hits:
        assert all(h.score == 0.0 for h in res.hits)
