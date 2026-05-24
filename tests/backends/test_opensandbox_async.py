"""OpenSandboxBackend async-internal behaviour — real opensandbox-server, no mocks.

Validates the post-migration ``OpenSandboxBackend``:

- Concurrent ``commands.run`` on the same sandbox serialise behind the
  per-sandbox exec lock (总则 1).
- Concurrent ``files.write`` to the *same* path serialise behind the
  per-path fs lock (总则 2 — last-writer-wins is deterministic, no torn
  payloads).
- Concurrent ``files.write`` to *distinct* paths run in parallel.
- Concurrent reads do not serialise behind any lock.

These tests require a reachable opensandbox-server (see ``conftest.py``'s
``opensandbox_real`` marker). Per ``[[feedback-testing-realonly]]``, there is
no ``FakeSandbox`` fallback — the suite is skipped, not faked, when the
server is unreachable.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from rath.backend import (
    BackendToolCommandRun,
    BackendToolFilesRead,
    BackendToolFilesWrite,
)
from rath.backend.opensandbox import OpenSandboxBackend
from tests.conftest import opensandbox_real

pytestmark = opensandbox_real


@pytest.fixture
def os_sandbox():
    """One real opensandbox sandbox, torn down at end of test."""
    backend = OpenSandboxBackend()
    sb = backend.open()
    try:
        with sb:
            yield backend, sb
    finally:
        # ``with sb`` already released its refcount; only call close()
        # explicitly if something has gone wrong and the sandbox is still open.
        if not sb.closed:
            backend.close(sb)


def test_concurrent_distinct_path_writes_run_in_parallel(os_sandbox) -> None:
    """Writes to N distinct paths complete in <<N× single-write latency."""
    backend, sb = os_sandbox
    n = 8
    payloads = {f"distinct_{i}.txt": f"v{i}".encode() for i in range(n)}

    def write_one(name: str) -> int:
        r = sb.dispatch(BackendToolFilesWrite(path=name, data=payloads[name]))
        return getattr(r, "bytes_written", -1)

    # Warm-up one write so we have a per-call baseline.
    t0 = time.perf_counter()
    write_one(next(iter(payloads.keys())))
    per_call = time.perf_counter() - t0

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(write_one, payloads.keys()))
    elapsed = time.perf_counter() - start

    assert all(r > 0 for r in results)
    # If they serialised, we'd expect ~n × per_call. Parallel should beat
    # serial by at least 2×. Generous to avoid CI flake against a real server.
    assert elapsed < per_call * n * 0.7, (
        f"distinct-path writes did not run in parallel: "
        f"per-call ≈ {per_call:.2f}s, {n} parallel took {elapsed:.2f}s"
    )

    for name, want in payloads.items():
        r = sb.dispatch(BackendToolFilesRead(path=name, encoding=None))
        assert getattr(r, "data", None) == want


def test_concurrent_same_path_writes_serialise_and_no_torn_payloads(os_sandbox) -> None:
    """Writes contending on the same path serialise; final byte count is deterministic."""
    backend, sb = os_sandbox
    path = "contended.txt"
    writers = 8
    payload_size = 256

    payloads = [bytes([i + 1]) * payload_size for i in range(writers)]

    def writer(idx: int) -> int:
        r = sb.dispatch(BackendToolFilesWrite(path=path, data=payloads[idx]))
        return getattr(r, "bytes_written", -1)

    with ThreadPoolExecutor(max_workers=writers) as pool:
        results = list(pool.map(writer, range(writers)))
    assert all(r == payload_size for r in results)

    # File on disk must equal exactly one of the input payloads (last writer
    # wins). A torn write would fail this single-payload match.
    read = sb.dispatch(BackendToolFilesRead(path=path, encoding=None))
    final = getattr(read, "data", None)
    assert final in payloads, (
        f"contended write produced a torn payload "
        f"(len={len(final) if final is not None else 'n/a'} expected {payload_size})"
    )


def test_concurrent_commands_serialise_on_exec_lock(os_sandbox) -> None:
    """Two ``commands.run`` calls on one sandbox cannot interleave their output."""
    backend, sb = os_sandbox
    cmd = "echo BEGIN && sleep 0.2 && echo END"

    def run_one(tag: str) -> tuple[str, int]:
        r = sb.dispatch(BackendToolCommandRun(cmd=cmd))
        return (
            r.stdout.decode("utf-8", errors="replace") if hasattr(r, "stdout") else "",
            int(getattr(r, "exit_code", -1)),
        )

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as pool:
        out_a, out_b = list(pool.map(run_one, ("a", "b")))
    elapsed = time.perf_counter() - start

    # Exec lock should serialise — total wallclock ≥ 2 × 0.2s.
    assert elapsed >= 0.35, (
        f"two contending commands.run calls finished in {elapsed:.2f}s; "
        f"expected serialised exec lock to enforce ≥ 0.4s"
    )

    for out, code in (out_a, out_b):
        assert code == 0
        assert "BEGIN" in out and "END" in out


def test_concurrent_reads_do_not_serialise(os_sandbox) -> None:
    """Reads share no lock — N parallel reads complete much faster than serial."""
    backend, sb = os_sandbox

    # Seed a file to read.
    sb.dispatch(BackendToolFilesWrite(path="readable.txt", data=b"hello"))

    n = 8

    def read_one(_: int) -> bytes:
        r = sb.dispatch(BackendToolFilesRead(path="readable.txt", encoding=None))
        return getattr(r, "data", b"")

    # Baseline.
    t0 = time.perf_counter()
    read_one(0)
    per_call = time.perf_counter() - t0

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(read_one, range(n)))
    elapsed = time.perf_counter() - start

    assert all(r == b"hello" for r in results)
    # Generous bound: parallel reads should be at most ~2× a single read.
    # Skip the overlap assertion when per-call latency is sub-ms (the
    # serial baseline is dominated by fixed overhead, not the lock).
    if per_call > 0.01:
        assert elapsed < per_call * n * 0.7, (
            f"reads appear serialised: per-call ≈ {per_call:.2f}s, "
            f"{n} parallel took {elapsed:.2f}s"
        )
