"""Deprecated thin shim around :class:`rath._async.runtime.OpenRathRuntime`.

The historical ``DedicatedEventLoopThread`` lived here so the OpenSandbox
backend had a private asyncio loop for its async-only SDK. As of the
async-runtime refactor, all OpenRath subsystems share a single process-wide
loop hosted by :class:`OpenRathRuntime`, which exposes the same blocking
``run(coro)`` semantics.

This module is kept for one release as a compatibility shim. New code MUST
import from :mod:`rath._async.runtime`.
"""

from __future__ import annotations

import warnings
from collections.abc import Coroutine
from typing import Any, TypeVar

from rath._async.runtime import OpenRathRuntime, runtime

T = TypeVar("T")


class DedicatedEventLoopThread:
    """Deprecated wrapper around the global :class:`OpenRathRuntime`.

    .. deprecated::
       Import :func:`rath._async.runtime.runtime` and call ``.run(coro)``
       directly. This class will be removed in a future release.
    """

    __slots__ = ("_rt",)

    def __init__(self) -> None:
        warnings.warn(
            "DedicatedEventLoopThread is deprecated; use "
            "rath._async.runtime.runtime() instead",
            DeprecationWarning,
            stacklevel=2,
        )
        self._rt: OpenRathRuntime = runtime()

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        return self._rt.run(coro)


def shared_opensandbox_loop() -> DedicatedEventLoopThread:
    """Deprecated accessor returning a wrapper over the process-wide runtime."""
    warnings.warn(
        "shared_opensandbox_loop() is deprecated; use "
        "rath._async.runtime.runtime() instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return DedicatedEventLoopThread()
