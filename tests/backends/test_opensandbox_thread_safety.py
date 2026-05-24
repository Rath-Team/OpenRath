"""Regression tests for ``OpenSandboxBackend.close`` thread-safety.

These tests do **not** require a reachable opensandbox server: they build
the backend, inject a fake native handle into ``_natives`` by hand, and
race ``close()`` from multiple threads.

Originally written against the sync ``close()`` + ``_natives_lock`` path
(see PR #11 contrib/pr5-sandbox-thread-safety). After the async-runtime
refactor (PR #18), ``close()`` is a sync facade over the async
``_aclose`` coroutine running on the shared
:class:`rath._async.runtime.OpenRathRuntime` event loop, so the
serialisation is structural: every ``_aclose`` hops onto the same loop
thread and runs to completion before the next picks up. We assert the
same property — native close is scheduled exactly once across concurrent
host-thread callers — through that surface.
"""

from __future__ import annotations

import threading
from typing import Any
from unittest.mock import MagicMock

from rath.backend.abc import BackendSandbox
from rath.backend.opensandbox import OpenSandboxBackend


def _fake_native(name: str = "fake") -> Any:
    """Async-mock native object whose kill()/close() are awaitable no-ops."""

    async def _noop() -> None:
        return None

    n = MagicMock(name=name)
    n.id = name
    n.kill = MagicMock(side_effect=lambda: _noop())
    n.close = MagicMock(side_effect=lambda: _noop())
    return n


def test_concurrent_close_calls_native_close_exactly_once() -> None:
    """Two host threads calling ``backend.close(sb)`` on the same sandbox
    must result in the native's kill/close being awaited exactly once.

    Under the async-runtime model both calls submit ``_aclose`` coroutines
    to the shared event loop. The first sets ``sandbox.closed=True`` and
    pops the native; the second observes ``sandbox.closed`` and returns
    early without re-popping or re-scheduling close.
    """
    backend = OpenSandboxBackend()
    native = _fake_native("handle-1")
    backend._natives[native.id] = native
    sandbox = BackendSandbox(backend=backend, handle=native.id, spec=None)

    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def _race() -> None:
        try:
            barrier.wait(timeout=2.0)
            backend.close(sandbox)
        except BaseException as exc:  # noqa: BLE001 -- collected for assertion
            errors.append(exc)

    threads = [threading.Thread(target=_race) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
        assert not t.is_alive(), "close() thread did not finish in time"

    assert not errors, f"close() raised in worker thread(s): {errors!r}"
    assert sandbox.closed is True
    assert native.id not in backend._natives
    assert native.kill.call_count == 1, (
        f"native.kill should be awaited exactly once, got {native.kill.call_count}"
    )
    assert native.close.call_count == 1, (
        f"native.close should be awaited exactly once, got {native.close.call_count}"
    )


def test_close_after_close_is_noop_same_thread() -> None:
    """Single-threaded sanity: double close on the same sandbox is a no-op."""
    backend = OpenSandboxBackend()
    native = _fake_native("handle-2")
    backend._natives[native.id] = native
    sandbox = BackendSandbox(backend=backend, handle=native.id, spec=None)

    backend.close(sandbox)
    backend.close(sandbox)

    assert sandbox.closed is True
    assert native.kill.call_count == 1
    assert native.close.call_count == 1
