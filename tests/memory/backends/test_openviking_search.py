"""Find / Search dispatch tests against a real OpenViking server."""

from __future__ import annotations

import os
import tempfile
import uuid

import pytest

from rath.memory import (
    MemoryExecutionFailure,
    MemoryFindResult,
    MemoryHit,
    MemoryOpFind,
    MemoryOpSearch,
    MemoryStore,
    MemoryStoreSpec,
)
from rath.memory.adapters.openviking import OpenVikingBackend

pytestmark = pytest.mark.openviking

_DB_FIXTURE = (
    "OpenRath database migration playbook: ALTER TABLE strategy, rolling "
    "deployments, online schema-change tools, replica catchup."
)
_WEATHER_FIXTURE = (
    "Weather report for the central plateau region: thunderstorms expected "
    "overnight with gusts reaching forty knots."
)


@pytest.fixture(scope="module")
def seeded_search_namespace(
    openviking_url: str, openviking_root_api_key: str
) -> dict[str, str]:
    import openviking as _ov

    ns = "osearch_" + uuid.uuid4().hex[:8]
    client = _ov.SyncHTTPClient(
        url=openviking_url,
        api_key=openviking_root_api_key,
        account="default",
        user_id="default",
        agent_id="default",
    )
    client.initialize()
    try:
        for label, content in [("db", _DB_FIXTURE), ("wx", _WEATHER_FIXTURE)]:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as fh:
                fh.write(content)
                local = fh.name
            try:
                client.add_resource(
                    local,
                    to=f"viking://resources/{ns}/{label}/",
                    wait=True,
                    timeout=90.0,
                )
            finally:
                os.unlink(local)
        try:
            client.wait_processed(timeout=60.0)
        except Exception:
            pass
    finally:
        client.close()
    return {"namespace_uri": f"viking://resources/{ns}"}


@pytest.fixture
def store(openviking_url: str, openviking_root_api_key: str) -> MemoryStore:
    backend = OpenVikingBackend()
    spec = MemoryStoreSpec(
        account_id="default",
        user_id="default",
        agent_id="default",
        options={"url": openviking_url, "api_key": openviking_root_api_key},
    )
    s = backend.open(spec)
    try:
        yield s
    finally:
        backend.close(s)


def test_find_returns_ranked_hits(
    store: MemoryStore, seeded_search_namespace: dict[str, str]
) -> None:
    op = MemoryOpFind(
        query="database migration playbook",
        target_uri=seeded_search_namespace["namespace_uri"],
        top_k=5,
    )
    result = store.dispatch(op)
    assert isinstance(result, MemoryFindResult)
    assert result.hits, "find should return at least one hit for the seeded corpus"
    top = result.hits[0]
    assert isinstance(top, MemoryHit)
    assert top.uri.startswith(seeded_search_namespace["namespace_uri"])
    assert top.score >= 0.0
    # The db fixture should outrank the weather one for this query.
    db_hits = [h for h in result.hits if "/db/" in h.uri]
    wx_hits = [h for h in result.hits if "/wx/" in h.uri]
    if db_hits and wx_hits:
        assert db_hits[0].score >= wx_hits[0].score


def test_find_honours_top_k(
    store: MemoryStore, seeded_search_namespace: dict[str, str]
) -> None:
    op = MemoryOpFind(
        query="thunderstorms",
        target_uri=seeded_search_namespace["namespace_uri"],
        top_k=1,
    )
    result = store.dispatch(op)
    assert isinstance(result, MemoryFindResult)
    assert len(result.hits) <= 1


def test_search_returns_ranked_hits(
    store: MemoryStore, seeded_search_namespace: dict[str, str]
) -> None:
    op = MemoryOpSearch(
        query="database migration playbook",
        target_uri=seeded_search_namespace["namespace_uri"],
        top_k=5,
    )
    result = store.dispatch(op)
    assert isinstance(result, MemoryFindResult)
    assert result.hits


def test_find_with_bogus_scope_returns_well_formed_result(
    store: MemoryStore,
) -> None:
    """The server tolerates an unknown sub-path inside ``viking://resources/``
    (returns empty hits). A truly invalid scope produces invalid_uri.
    Either is fine; this test pins both behaviours under one assertion."""
    op = MemoryOpFind(
        query="anything",
        target_uri="viking://bogus_scope_xyz/",
        top_k=3,
    )
    result = store.dispatch(op)
    assert isinstance(result, (MemoryFindResult, MemoryExecutionFailure))
    if isinstance(result, MemoryExecutionFailure):
        assert result.kind in {"invalid_uri", "not_found"}
