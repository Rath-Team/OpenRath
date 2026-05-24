"""Reference counting on :class:`BackendSandbox` — real LocalBackend + OpenSandbox.

Verifies the unified refcount lifecycle: ``acquire()`` increments, ``release()``
decrements, and the backend is told to close exactly when the count hits zero.
``with sandbox:`` is the context-manager equivalent — ``__enter__`` acquires,
``__exit__`` releases. There is no "force close" escape hatch.
"""

from __future__ import annotations

import threading

import pytest

from rath.backend import get
from rath.backend.errors import BackendSandboxClosed
from tests.conftest import opensandbox_real


def test_open_returns_zero_refcount() -> None:
    backend = get("local")
    sb = backend.open()
    try:
        assert sb.refcount == 0
        assert not sb.closed
    finally:
        backend.close(sb)


def test_acquire_then_release_closes_via_backend() -> None:
    backend = get("local")
    sb = backend.open()
    sb.acquire()
    assert sb.refcount == 1
    assert not sb.closed
    sb.release()
    assert sb.closed
    assert backend.sandbox_count() == 0


def test_multiple_acquires_require_matching_releases() -> None:
    backend = get("local")
    sb = backend.open()
    sb.acquire()
    sb.acquire()
    sb.acquire()
    assert sb.refcount == 3
    sb.release()
    assert sb.refcount == 2
    assert not sb.closed
    sb.release()
    assert sb.refcount == 1
    assert not sb.closed
    sb.release()
    assert sb.closed


def test_context_manager_acquires_and_releases() -> None:
    backend = get("local")
    sb = backend.open()
    with sb:
        assert sb.refcount == 1
        assert not sb.closed
    assert sb.closed


def test_nested_context_managers_share_refcount() -> None:
    backend = get("local")
    sb = backend.open()
    with sb:
        assert sb.refcount == 1
        with sb:
            assert sb.refcount == 2
            assert not sb.closed
        assert sb.refcount == 1
        assert not sb.closed
    assert sb.closed


def test_acquire_after_close_raises() -> None:
    backend = get("local")
    sb = backend.open()
    sb.acquire()
    sb.release()
    assert sb.closed
    with pytest.raises(BackendSandboxClosed):
        sb.acquire()


def test_release_after_close_is_noop() -> None:
    backend = get("local")
    sb = backend.open()
    sb.acquire()
    sb.release()
    assert sb.closed
    sb.release()
    sb.release()
    assert sb.closed


def test_explicit_backend_close_marks_closed() -> None:
    """The low-level :meth:`Backend.close` still works for callers who manage
    lifetimes manually (no Session, no context manager). After that, refcount
    becomes meaningless (release/acquire short-circuit on ``closed``)."""
    backend = get("local")
    sb = backend.open()
    backend.close(sb)
    assert sb.closed


def test_concurrent_acquire_release_is_safe() -> None:
    """Hammer acquire/release from many threads; refcount must stay coherent.

    Each thread acquires then releases ``iters`` times. The sandbox starts
    with one extra reference held by the main thread so the count never
    reaches zero mid-test (we want to verify the lock under contention, not
    the close-on-zero edge). At the end exactly one final release should
    close the sandbox.
    """
    backend = get("local")
    sb = backend.open()
    sb.acquire()  # baseline ref so the count can't drain to zero mid-test

    threads = 8
    iters = 1000

    def worker() -> None:
        for _ in range(iters):
            sb.acquire()
            sb.release()

    workers = [threading.Thread(target=worker) for _ in range(threads)]
    for t in workers:
        t.start()
    for t in workers:
        t.join()

    assert sb.refcount == 1
    assert not sb.closed
    sb.release()
    assert sb.closed
    assert backend.sandbox_count() == 0


@opensandbox_real
@pytest.mark.opensandbox
def test_opensandbox_refcount_real_server() -> None:
    backend = get("opensandbox")
    sb = backend.open()
    try:
        assert sb.refcount == 0
        sb.acquire()
        assert sb.refcount == 1
        sb.acquire()
        assert sb.refcount == 2
        sb.release()
        assert sb.refcount == 1
        assert not sb.closed
        assert backend.sandbox_count() == 1
        sb.release()
        assert sb.closed
        assert backend.sandbox_count() == 0
    finally:
        if not sb.closed:
            backend.close(sb)


@opensandbox_real
@pytest.mark.opensandbox
def test_opensandbox_context_manager_real_server() -> None:
    backend = get("opensandbox")
    with backend.open() as sb:
        assert sb.refcount == 1
        assert not sb.closed
        assert backend.sandbox_count() == 1
    assert sb.closed
    assert backend.sandbox_count() == 0
