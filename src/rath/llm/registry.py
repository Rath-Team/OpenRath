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
]

ChatClientFactory = Callable[[Provider], ChatClient]

_FACTORIES: dict[str, ChatClientFactory] = {}
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
    with _FACTORIES_LOCK:
        try:
            factory = _FACTORIES[kind]
        except KeyError as e:
            raise ValueError(
                f"unknown provider_kind={kind!r}; "
                f"registered kinds: {sorted(_FACTORIES)}",
            ) from e
    return factory(provider)


def registered_kinds() -> tuple[str, ...]:
    """Snapshot of currently registered kinds (useful for diagnostics / tests)."""
    with _FACTORIES_LOCK:
        return tuple(sorted(_FACTORIES))
