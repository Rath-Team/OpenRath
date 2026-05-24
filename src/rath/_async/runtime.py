"""Process-wide background asyncio loop with sync ``submit`` / ``run``.

``OpenRathRuntime`` hosts one daemon thread running an asyncio event loop.
All async work in OpenRath (backend dispatch, LLM completions, session loops,
persistence writers) is funnelled through this loop so that:

- Multiple coroutines share one loop and run truly concurrently (no per-call
  thread-pool spin-up, no ad-hoc ``asyncio.run`` per call).
- Synchronous user code keeps calling synchronous OpenRath APIs; the runtime
  is the only place that has to know coroutines exist.

Concurrency-safety rules this module enforces (阶段 0 of the plan):

- ``submit(coro)`` returns a ``concurrent.futures.Future`` and never blocks.
- ``run(coro)`` blocks the calling thread. If the caller is *itself* inside
  a running asyncio loop, blocking would deadlock that loop; we raise
  instead. The session loop / backend dispatch path never calls ``run``
  recursively — only sync facades on the host thread do — so this is the
  correct behavior.
- ``drain(timeout)`` waits for in-flight futures and cancels stragglers on
  timeout (总则 8 — cancellation semantics for atexit / explicit shutdown).
- ``shutdown()`` stops the loop and joins the thread.
"""

from __future__ import annotations

import asyncio
import atexit
import concurrent.futures
import threading
import weakref
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


class OpenRathRuntime:
    """Single background asyncio loop, shared across all OpenRath subsystems."""

    __slots__ = (
        "_loop",
        "_ready",
        "_thread",
        "_inflight",
        "_inflight_lock",
        "_shut_down",
        "__weakref__",
    )

    def __init__(self, *, thread_name: str = "rath-runtime") -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()
        self._shut_down = False
        # Weak set so a leaked future does not pin objects. Iteration is
        # guarded by ``_inflight_lock`` for thread safety; the set itself
        # tolerates concurrent ``add`` (CPython detail) but copy-on-iterate.
        self._inflight: weakref.WeakSet[concurrent.futures.Future[Any]] = (
            weakref.WeakSet()
        )
        self._inflight_lock = threading.Lock()

        def _runner() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._ready.set()
            try:
                loop.run_forever()
            finally:
                try:
                    loop.close()
                except Exception:  # pragma: no cover -- best-effort close
                    pass

        self._thread = threading.Thread(
            target=_runner,
            daemon=True,
            name=thread_name,
        )
        self._thread.start()
        if not self._ready.wait(timeout=60.0):
            raise RuntimeError("OpenRathRuntime background loop failed to start")
        if self._loop is None:
            raise RuntimeError("OpenRathRuntime loop is unset after ready")

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """The background event loop. Public for advanced introspection only."""
        loop = self._loop
        if loop is None:
            raise RuntimeError("runtime has not started")
        return loop

    def submit(self, coro: Coroutine[Any, Any, T]) -> concurrent.futures.Future[T]:
        """Schedule ``coro`` on the background loop; return a sync Future.

        Never blocks. Safe to call from any thread, including from inside
        another asyncio loop.
        """
        if self._shut_down:
            raise RuntimeError("OpenRathRuntime is shut down; cannot submit")
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
        with self._inflight_lock:
            self._inflight.add(fut)
        return fut

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        """Block the calling thread until ``coro`` completes; return its result.

        Raises ``RuntimeError`` when called from inside a running asyncio loop,
        because blocking the caller's loop on a different loop's future would
        deadlock. This is the boundary that keeps the public sync façade safe.
        """
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is not None:
            raise RuntimeError(
                "OpenRathRuntime.run() called from inside an asyncio loop; "
                "OpenRath's public API is synchronous and must be called from "
                "a non-async context. Run your OpenRath calls from a regular "
                "thread, or from `asyncio.to_thread(...)` if you must call "
                "them from async code."
            )
        return self.submit(coro).result()

    def drain(self, timeout: float | None = None) -> int:
        """Wait for in-flight futures to finish; cancel survivors on timeout.

        Returns the number of futures cancelled (0 on a clean drain). Safe to
        call multiple times.
        """
        with self._inflight_lock:
            snapshot = [f for f in list(self._inflight) if not f.done()]
        if not snapshot:
            return 0
        done, not_done = concurrent.futures.wait(snapshot, timeout=timeout)
        cancelled = 0
        for f in not_done:
            if f.cancel():
                cancelled += 1
        return cancelled

    def shutdown(self) -> None:
        """Stop the loop and join the background thread."""
        if self._shut_down:
            return
        self._shut_down = True
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        self._thread.join(timeout=5.0)


_GLOBAL_RUNTIME: OpenRathRuntime | None = None
_GLOBAL_LOCK = threading.Lock()


def runtime() -> OpenRathRuntime:
    """Return the process-wide :class:`OpenRathRuntime`, starting it on first use."""
    global _GLOBAL_RUNTIME
    rt = _GLOBAL_RUNTIME
    if rt is not None:
        return rt
    with _GLOBAL_LOCK:
        if _GLOBAL_RUNTIME is None:
            _GLOBAL_RUNTIME = OpenRathRuntime()
        return _GLOBAL_RUNTIME


@atexit.register
def _shutdown_global_runtime() -> None:  # pragma: no cover -- interpreter exit
    rt = _GLOBAL_RUNTIME
    if rt is None:
        return
    try:
        rt.drain(5.0)
    finally:
        rt.shutdown()
