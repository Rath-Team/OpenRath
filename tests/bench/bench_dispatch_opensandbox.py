"""Micro-benchmarks against a real opensandbox-server.

Mirrors :mod:`bench_dispatch_local` against the remote sandbox so we can
spot per-call latency regressions in the async OpenSandbox path
(``OpenSandboxBackend._adispatch``). Skipped automatically when the
server is unreachable — never falls back to mocks (see
``[[feedback-testing-realonly]]``).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from rath.backend import BackendToolFilesRead, BackendToolFilesWrite
from tests.conftest import opensandbox_real

pytestmark = [pytest.mark.bench, opensandbox_real]


@pytest.fixture(scope="module")
def _os_sandbox() -> Any:
    # Importing inside the fixture so collection-time import errors when
    # the optional dep is missing degrade to a clean skip via the marker.
    from rath.backend.opensandbox import OpenSandboxBackend

    backend = OpenSandboxBackend()
    sb = backend.open()
    sb.dispatch(BackendToolFilesWrite(path="_bench.txt", data=b"opensandbox bench\n"))
    try:
        yield sb
    finally:
        backend.close(sb)


def test_bench_opensandbox_read_single(benchmark: Any, _os_sandbox: Any) -> None:
    call = BackendToolFilesRead(path="_bench.txt")

    def _one() -> None:
        _os_sandbox.dispatch(call)

    benchmark(_one)


@pytest.mark.parametrize("workers", [1, 4, 16])
def test_bench_opensandbox_read_fanout(
    benchmark: Any, _os_sandbox: Any, workers: int
) -> None:
    call = BackendToolFilesRead(path="_bench.txt")
    pool = ThreadPoolExecutor(max_workers=workers)

    def _fanout() -> None:
        futs = [pool.submit(_os_sandbox.dispatch, call) for _ in range(workers)]
        for f in futs:
            f.result()

    try:
        benchmark(_fanout)
    finally:
        pool.shutdown(wait=True)
