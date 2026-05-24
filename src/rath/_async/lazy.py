"""Lazy materialization handle for :class:`~rath.session.Session`.

When the public :func:`~rath.session.loop.run_session_loop` returns, the
work is still running on :class:`~rath.\_async.runtime.OpenRathRuntime`.
The returned :class:`Session` carries a :class:`LazyValue` in
``_pending``; reading :attr:`Session.chunk_table` /
:attr:`Session.cumulative_usage` calls :meth:`Session.synchronize` which
blocks on this :class:`LazyValue` and writes the result into the
session's materialized fields.

PyTorch CUDA Stream analogue: ``runtime().submit(coro)`` schedules work
on the loop and returns a sync :class:`concurrent.futures.Future`;
``LazyValue.result()`` is the implicit ``synchronize()`` call.

Concurrency-safety invariants (per 阶段 0 of the plan):

- The future's ``add_done_callback`` runs on the runtime loop thread.
  ``unraisable_warn`` is a callback installed by :class:`Session` to
  surface dropped failures (no one ever called ``synchronize``) as
  ``warnings.warn`` + ``logger.exception``, not as silent loss.
- ``LazyValue.consumed`` is flipped by :class:`Session.synchronize` (in
  the host thread under ``_sync_lock``) so the unraisable callback can
  tell "result was observed" from "result was dropped". The flip is
  monotonic and idempotent.
"""

from __future__ import annotations

import concurrent.futures
import logging
import threading
import warnings
from typing import Any, Generic, TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)

__all__ = ["LazyValue", "unraisable_warn"]


class LazyValue(Generic[T]):
    """Sync-thread-facing wrapper over a :class:`concurrent.futures.Future`."""

    __slots__ = ("_future", "_consumed", "_consumed_lock")

    def __init__(self, future: concurrent.futures.Future[T]) -> None:
        self._future = future
        self._consumed = False
        self._consumed_lock = threading.Lock()

    @property
    def future(self) -> concurrent.futures.Future[T]:
        return self._future

    def done(self) -> bool:
        return self._future.done()

    @property
    def consumed(self) -> bool:
        return self._consumed

    def mark_consumed(self) -> None:
        """Idempotently flag the result as observed by ``synchronize()``."""
        with self._consumed_lock:
            self._consumed = True

    def result(self, timeout: float | None = None) -> T:
        """Block for the future; raise its exception or return its value."""
        return self._future.result(timeout=timeout)

    def exception(self, timeout: float | None = None) -> BaseException | None:
        return self._future.exception(timeout=timeout)

    def add_done_callback(self, fn: Any) -> None:  # pragma: no cover -- thin proxy
        self._future.add_done_callback(fn)


def unraisable_warn(lazy: LazyValue[Any], session_id: Any) -> None:
    """Emit a warning if ``lazy`` failed but no one ever called ``synchronize()``.

    Installed via ``Session.__del__`` and as the future's done-callback for
    sessions whose ``_pending`` has not been observed. Triggering condition:
    ``future`` finished with an exception **and** ``mark_consumed`` was never
    called.
    """
    if lazy.consumed:
        return
    if not lazy.done():
        return
    exc = lazy.exception()
    if exc is None:
        return
    msg = (
        f"Session {session_id!s} pending future raised "
        f"{type(exc).__name__}({exc}) but was never synchronize()d; the "
        f"error has been dropped. Call session.synchronize() or read "
        f"session.chunk_table to surface it."
    )
    logger.error(msg, exc_info=(type(exc), exc, exc.__traceback__))
    warnings.warn(msg, RuntimeWarning, stacklevel=2)
