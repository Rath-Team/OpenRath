"""LocalBackend async-internal behaviour — real subprocess + filesystem, no mocks.

Validates the post-migration LocalBackend (``_aopen`` / ``_aclose`` / ``_adispatch``):

- Concurrent ``dispatch`` calls through the sync facade run truly in parallel
  (they unblock simultaneously, so total wallclock ≪ N × per-call latency).
- The async hooks can be awaited directly on the runtime loop without going
  through the sync facade — verifies the public sync path and the internal
  async path produce identical results.
- Sandbox handle bookkeeping stays consistent under concurrent open/close
  storms.

These tests exercise real subprocesses and real files on disk; there is no
mock or fake subprocess runner. See ``[[feedback-testing-realonly]]``.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from rath._async.runtime import runtime
from rath.backend import (
    BackendToolCommandRun,
    BackendToolFilesRead,
    BackendToolFilesWrite,
)
from rath.backend.local import LocalBackend


def _sleep_cmd(seconds: float) -> list[str]:
    """Return a portable argv that sleeps for ``seconds`` and exits 0."""
    return [
        sys.executable,
        "-c",
        f"import time; time.sleep({seconds})",
    ]


def test_concurrent_dispatch_runs_in_parallel() -> None:
    """N=8 parallel ``commands.run`` calls finish in roughly one sleep, not N."""
    backend = LocalBackend()
    sleep_s = 0.5
    workers = 8
    with backend.open() as sb:
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(sb.dispatch, BackendToolCommandRun(cmd=_sleep_cmd(sleep_s)))
                for _ in range(workers)
            ]
            results = [f.result() for f in futures]
        elapsed = time.perf_counter() - start
    # Parallelism check: total wallclock must be well under the serial cost.
    # Generous bound to avoid CI flake — serial would be ~4 s, parallel ~0.5 s.
    assert elapsed < sleep_s * workers / 2, (
        f"expected parallel execution, but {workers} × {sleep_s}s sleeps "
        f"took {elapsed:.2f}s wallclock"
    )
    for r in results:
        assert hasattr(r, "exit_code") and r.exit_code == 0


def test_concurrent_open_close_preserves_handle_bookkeeping() -> None:
    """Many concurrent ``open()`` / ``close()`` cycles leave no leaked handles."""
    backend = LocalBackend()
    cycles = 32

    def cycle() -> None:
        sb = backend.open()
        backend.close(sb)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: cycle(), range(cycles)))

    assert backend.sandbox_count() == 0, (
        f"expected no live sandboxes after {cycles} open/close cycles, "
        f"got {backend.sandbox_count()}"
    )


def test_concurrent_writes_to_distinct_paths_dont_clobber(tmp_path) -> None:
    """Concurrent writes to different files all land with the expected payload."""
    backend = LocalBackend()
    n_files = 16
    with backend.open() as sb:
        payloads = {f"f{i}.txt": f"payload-{i}".encode("utf-8") for i in range(n_files)}

        def write_one(name: str) -> None:
            r = sb.dispatch(BackendToolFilesWrite(path=name, data=payloads[name]))
            assert getattr(r, "bytes_written", -1) == len(payloads[name])

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(write_one, payloads.keys()))

        # All reads back match — no torn writes, no swapped contents.
        for name, want in payloads.items():
            r = sb.dispatch(BackendToolFilesRead(path=name, encoding=None))
            assert getattr(r, "data", None) == want


def test_internal_async_hooks_match_sync_facade(tmp_path) -> None:
    """``runtime().run(backend._adispatch(...))`` matches ``sb.dispatch(...)``."""
    backend = LocalBackend()
    rt = runtime()
    with backend.open() as sb:
        # Sync facade
        sync_r = sb.dispatch(BackendToolFilesWrite(path="via_sync.txt", data="hello"))
        assert getattr(sync_r, "bytes_written", -1) == 5

        # Internal async hook
        async_r = rt.run(
            backend._adispatch(
                sb, BackendToolFilesWrite(path="via_async.txt", data="hi")
            )
        )
        assert getattr(async_r, "bytes_written", -1) == 2

        # Both files exist on disk.
        sync_read = sb.dispatch(
            BackendToolFilesRead(path="via_sync.txt", encoding=None)
        )
        async_read = sb.dispatch(
            BackendToolFilesRead(path="via_async.txt", encoding=None)
        )
        assert getattr(sync_read, "data", None) == b"hello"
        assert getattr(async_read, "data", None) == b"hi"


def test_runtime_run_rejects_call_from_inside_loop() -> None:
    """``runtime().run`` must refuse to deadlock the caller's own asyncio loop.

    Per 阶段 0 boundary: the sync facade is only safe from a non-async caller.
    If a user manages to call into the facade from inside their own running
    loop, OpenRath must raise instead of hanging the whole loop.
    """
    rt = runtime()

    async def attempt() -> None:
        # Call the sync run() from inside an asyncio loop on the caller's
        # thread. This is the failure mode we want to surface explicitly.
        coro = asyncio.sleep(0)
        try:
            rt.run(coro)
        finally:
            coro.close()

    with pytest.raises(RuntimeError, match="inside an asyncio loop"):
        asyncio.run(attempt())


def test_dispatch_from_many_threads_does_not_leak_threads() -> None:
    """Repeated parallel dispatch must not balloon ``threading.active_count()``.

    A naive impl that spins up a fresh executor per call would leak threads;
    the runtime + asyncio.to_thread pooling should keep the count bounded.
    """
    backend = LocalBackend()
    rounds = 4
    workers = 8
    baseline = threading.active_count()
    with backend.open() as sb:
        for _ in range(rounds):
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(
                    pool.map(
                        lambda _: sb.dispatch(
                            BackendToolFilesWrite(path="a.txt", data="x")
                        ),
                        range(workers),
                    )
                )
    # Allow some room for the runtime's loop thread + asyncio's default
    # thread-pool. The point of the assertion is "didn't grow unboundedly",
    # not exact equality.
    grew_by = threading.active_count() - baseline
    assert grew_by < 64, (
        f"threading.active_count grew by {grew_by} after {rounds} × {workers} "
        f"dispatches — possible thread leak"
    )
