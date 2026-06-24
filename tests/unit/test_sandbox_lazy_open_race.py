"""Lazy sandbox open must be race-free under parallel first-use tool calls.

When several ``parallel_safe`` tools fire on the very first tool round, each
calls ``require_sandbox()`` -> ``_ensure_sandbox()`` at once. Without a lock,
two threads both pass the "is it open?" check, both open + acquire a backend
sandbox, and the loser is silently orphaned (an acquired handle, never
released). The double-checked lock guarantees exactly one open. A small sleep
injected into the backend's ``open`` widens the race window so a regression
(removing the lock) fails reliably rather than flaking green.
"""

from __future__ import annotations

import threading
import time

from rath.backend import get
from rath.session import Session


def test_concurrent_ensure_sandbox_opens_once(monkeypatch) -> None:
    backend = get("local")
    real_open = backend.open
    n = 8
    # All workers line up here, then enter _ensure_sandbox together.
    barrier = threading.Barrier(n)

    open_calls = 0
    open_calls_lock = threading.Lock()

    def slow_open(*args, **kwargs):
        # Widen the open window so that, absent the lock, several threads
        # would pass the "is it open?" check before the first assigns.
        nonlocal open_calls
        with open_calls_lock:
            open_calls += 1
        time.sleep(0.02)
        return real_open(*args, **kwargs)

    monkeypatch.setattr(backend, "open", slow_open)

    session = Session.from_user_message("hi").to("local")
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            barrier.wait(timeout=5)
            session.require_sandbox()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    try:
        assert not errors, f"require_sandbox raised under contention: {errors}"
        # The lock must let exactly one thread open + acquire; the rest see the
        # already-open handle. ``sandbox_count()`` is a process-global singleton
        # counter (polluted by other tests), so assert on opens *we* caused.
        assert open_calls == 1, f"expected one open, got {open_calls}"
        assert session.sandbox is not None
        assert session.sandbox.refcount == 1
    finally:
        session.close_sandbox()
