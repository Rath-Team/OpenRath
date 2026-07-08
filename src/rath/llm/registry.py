"""Registry mapping :attr:`Provider.provider_kind` to a :class:`ChatClient` factory.

Built-in adapters (``"openai"``, ``"anthropic"``) self-register on import of
:mod:`rath.llm.openai` / :mod:`rath.llm.anthropic`, which :mod:`rath.llm` does
eagerly. Third parties can call :func:`register_chat_client` to add their own
without modifying core.

The single dispatch point :func:`chat_client_for` replaces the previous
``provider.provider_kind == "anthropic"`` string check that lived in
:mod:`rath.session.loop`.
"""

from __future__ import annotations

import threading
from typing import Callable

from rath.llm.base import ChatClient
from rath.llm.provider import Provider

__all__ = [
    "ChatClientFactory",
    "register_chat_client",
    "chat_client_for",
    "registered_kinds",
    "clear_client_cache",
]

ChatClientFactory = Callable[[Provider], ChatClient]

_FACTORIES: dict[str, ChatClientFactory] = {}

# Constructed-client cache. Keyed on the provider's HTTP-identity fields so a
# reused provider does not rebuild the SDK client on every loop run. Only
# providers with an EXPLICIT api_key are cached: a provider that leaves api_key
# empty resolves credentials from env/config at construction time, and env can
# change within a process, so caching such a client could serve a stale one.
_CLIENT_CACHE: dict[tuple[str, str, str, str], ChatClient] = {}
_CACHE_LOCK = threading.Lock()


def _cache_key(provider: Provider) -> tuple[str, str, str, str] | None:
    """Identity key for caching, or ``None`` when the provider must not be cached."""
    if not provider.api_key:
        return None  # env/config fallback — never cache (could go stale)
    return (
        provider.provider_kind or "openai",
        provider.base_url or "",
        provider.api_key,
        provider.model or "",
    )


def clear_client_cache() -> None:
    """Drop all cached clients (call after rebinding credentials / in tests)."""
    with _CACHE_LOCK:
        _CLIENT_CACHE.clear()


# Guards reads from / writes to ``_FACTORIES`` only. Deliberately does
# **not** wrap ``factory(provider)`` in :func:`chat_client_for` — built-in
# factories (``RathOpenAIChatClient``, ``RathAnthropicChatClient``) are
# lightweight wrappers around the underlying SDK clients and serializing
# their construction would block parallel callers for no benefit. If you
# register a factory that needs serialization (e.g. one that calls out
# to a remote service), wrap that side effect with your own lock inside
# the factory.
_FACTORIES_LOCK = threading.Lock()


def register_chat_client(kind: str, factory: ChatClientFactory) -> None:
    """Register ``factory(provider) -> ChatClient`` under ``kind``.

    Overwrites any previous registration silently — late imports therefore
    win. Built-in kinds (``"openai"``, ``"anthropic"``) are registered when
    their subpackages are imported by :mod:`rath.llm`.
    """
    with _FACTORIES_LOCK:
        _FACTORIES[kind] = factory


def chat_client_for(provider: Provider) -> ChatClient:
    """Return the :class:`ChatClient` for ``provider.provider_kind``.

    ``provider.provider_kind=None`` defaults to ``"openai"``. Unknown kinds
    raise ``ValueError`` listing what is currently registered.
    """
    kind = provider.provider_kind or "openai"
    key = _cache_key(provider)
    if key is not None:
        with _CACHE_LOCK:
            cached = _CLIENT_CACHE.get(key)
            if cached is not None:
                return cached
    with _FACTORIES_LOCK:
        try:
            factory = _FACTORIES[kind]
        except KeyError as e:
            raise ValueError(
                f"unknown provider_kind={kind!r}; "
                f"registered kinds: {sorted(_FACTORIES)}",
            ) from e
    client = factory(provider)
    if key is not None:
        with _CACHE_LOCK:
            # Another thread may have built one concurrently; keep the first.
            client = _CLIENT_CACHE.setdefault(key, client)
    return client


def registered_kinds() -> tuple[str, ...]:
    """Snapshot of currently registered kinds (useful for diagnostics / tests)."""
    with _FACTORIES_LOCK:
        return tuple(sorted(_FACTORIES))
