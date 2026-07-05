"""P4.1 — optional client cache in chat_client_for.

Constructing a fresh SDK client on every loop run is wasteful when the same
provider identity is reused. We cache the constructed ChatClient keyed on the
provider's HTTP-identity fields — but ONLY when the Provider carries an
explicit api_key, so a provider relying on env/config fallback is never served
a stale client (env can change mid-process; an explicit-key provider cannot go
stale). A helper clears the cache for tests / rebinds.
"""

from __future__ import annotations

from typing import Iterator

import pytest

from rath.llm.provider import Provider
from rath.llm.registry import chat_client_for, clear_client_cache


@pytest.fixture(autouse=True)
def _clear() -> Iterator[None]:
    clear_client_cache()
    yield
    clear_client_cache()


def test_identical_explicit_providers_share_client() -> None:
    p1 = Provider(provider_kind="openai", base_url="https://x/v1", api_key="sk-a")
    p2 = Provider(provider_kind="openai", base_url="https://x/v1", api_key="sk-a")
    c1 = chat_client_for(p1)
    c2 = chat_client_for(p2)
    assert c1 is c2  # cache hit on identical identity


def test_differing_identity_distinct_clients() -> None:
    c1 = chat_client_for(Provider(base_url="https://x/v1", api_key="sk-a"))
    c2 = chat_client_for(Provider(base_url="https://x/v1", api_key="sk-b"))
    c3 = chat_client_for(Provider(base_url="https://y/v1", api_key="sk-a"))
    assert c1 is not c2
    assert c1 is not c3


def test_clear_invalidates() -> None:
    p = Provider(base_url="https://x/v1", api_key="sk-a")
    c1 = chat_client_for(p)
    clear_client_cache()
    c2 = chat_client_for(p)
    assert c1 is not c2


def test_fallback_provider_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Provider with no explicit api_key relies on env/config and must NOT be
    cached (otherwise it could be served a client built against stale env)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://env/v1")
    p = Provider(provider_kind="openai")  # api_key=None → fallback
    c1 = chat_client_for(p)
    c2 = chat_client_for(p)
    assert c1 is not c2  # not cached
