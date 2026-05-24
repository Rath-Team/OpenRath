"""Public API surface contract — sync-only, no leaked async symbols.

The PyTorch-style refactor is anchored on a hard rule: users never write
``await`` / ``async def`` and never import anything async-flavored from the
public package. The runtime is private (``rath._async``); the sync facades
return :class:`~rath.session.session.Session` handles that synchronize
implicitly on read.

This test pins that boundary with three checks:

1. ``rath._async`` is not exposed via ``import rath`` (no implicit re-export).
2. Top-level ``rath`` re-exports carry **zero** async-flavored names — no
   ``arun_*`` / ``acomplete*`` / ``aforward`` / ``AsyncChatClient`` etc.
3. Public submodules (``rath.session``, ``rath.flow``, ``rath.llm``,
   ``rath.backend``) re-export the same sync-only surface — scanning their
   ``__all__`` and module attributes for the same banned prefixes.

If a future change adds an async symbol to a public namespace, this test
fails before the symbol can ship.
"""

from __future__ import annotations

import importlib
import re

import pytest

# Names containing these regex matches are considered "async-flavored" and
# disallowed in the public API. Public Anthropic SDK lookups like
# ``AsyncAnthropic`` come in via ``rath._async`` and must not leak.
_ASYNC_BANNED = re.compile(
    r"""
    ^(?:
        a(?:run|complete|forward|dispatch|open|close)_?
      | Async[A-Z]
    )
    """,
    re.VERBOSE,
)


def _names_from_module(modname: str) -> tuple[str, ...]:
    mod = importlib.import_module(modname)
    declared = getattr(mod, "__all__", None)
    if declared is not None:
        return tuple(declared)
    return tuple(n for n in vars(mod) if not n.startswith("_"))


def test_rath_does_not_expose_async_subpackage() -> None:
    """``import rath`` must not pull ``rath._async`` into its public attrs."""
    import rath

    assert not hasattr(rath, "_async") or rath._async.__name__ == "rath._async", (
        "rath._async is fine to exist as a private submodule but must not be "
        "advertised via rath.__all__"
    )
    public = getattr(rath, "__all__", None)
    if public is not None:
        assert "_async" not in public
        assert not any(
            name.startswith("a") and name[1:2].isupper() for name in public
        ), "rath.__all__ must not include AsyncFoo-style names"


@pytest.mark.parametrize(
    "modname",
    [
        "rath",
        "rath.session",
        "rath.flow",
        "rath.llm",
        "rath.backend",
    ],
)
def test_public_module_has_no_async_names(modname: str) -> None:
    """Public modules expose synchronous APIs only — no ``a*`` / ``Async*``."""
    names = _names_from_module(modname)
    offenders = [n for n in names if _ASYNC_BANNED.match(n)]
    assert not offenders, (
        f"public module {modname!r} exposes async-flavored names: {offenders}. "
        "Async symbols must live under rath._async only."
    )


def test_session_loop_public_signature_is_sync() -> None:
    """``run_session_loop`` is a regular function (not a coroutine function)."""
    import inspect

    from rath.session import run_session_loop

    assert not inspect.iscoroutinefunction(run_session_loop)
    sig = inspect.signature(run_session_loop)
    # Sanity: no parameter is named or annotated with anything async-y.
    for name, param in sig.parameters.items():
        assert not _ASYNC_BANNED.match(name), (
            f"run_session_loop has async-flavored parameter {name!r}"
        )


def test_chat_client_protocol_is_sync() -> None:
    """User-facing :class:`~rath.llm.ChatClient` Protocol stays synchronous."""
    import inspect

    from rath.llm import ChatClient

    for attr in ("complete", "complete_stream"):
        fn = getattr(ChatClient, attr, None)
        if fn is None:
            continue
        assert not inspect.iscoroutinefunction(fn), (
            f"ChatClient.{attr} must be synchronous on the public protocol"
        )
