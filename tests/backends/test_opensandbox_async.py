"""OpenSandboxBackend async-internal behaviour — real opensandbox-server, no mocks.

Validates the post-migration ``OpenSandboxBackend``:

- Concurrent ``commands.run`` on the same sandbox serialise behind the
  per-sandbox exec lock.
- Concurrent ``files.write`` to the *same* path serialise behind the
  per-path fs lock (last-writer-wins is deterministic; no torn payloads).
- Concurrent ``files.write`` to *distinct* paths do not clobber one another.
- Concurrent reads return complete payloads under thread contention.

These tests require a reachable opensandbox-server (see ``conftest.py``'s
``opensandbox_real`` marker). There is no ``FakeSandbox`` fallback — the suite
is skipped, not faked, when the server is unreachable.
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

pytestmark = [opensandbox_real, pytest.mark.opensandbox]


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


def test_concurrent_distinct_path_writes_do_not_clobber(os_sandbox) -> None:
    """Concurrent writes to N distinct paths all commit their own payload."""
    backend, sb = os_sandbox
    n = 8
    payloads = {f"distinct_{i}.txt": f"v{i}".encode() for i in range(n)}

    def write_one(name: str) -> int:
        r = sb.dispatch(BackendToolFilesWrite(path=name, data=payloads[name]))
        return getattr(r, "bytes_written", -1)

    with ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(write_one, payloads.keys()))

    assert all(r > 0 for r in results)

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


def test_concurrent_reads_return_complete_payloads(os_sandbox) -> None:
    """N concurrent reads all return the complete payload."""
    backend, sb = os_sandbox

    # Seed a file to read.
    sb.dispatch(BackendToolFilesWrite(path="readable.txt", data=b"hello"))

    n = 8

    def read_one(_: int) -> bytes:
        r = sb.dispatch(BackendToolFilesRead(path="readable.txt", encoding=None))
        return getattr(r, "data", b"")

    with ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(read_one, range(n)))

    assert all(r == b"hello" for r in results)
