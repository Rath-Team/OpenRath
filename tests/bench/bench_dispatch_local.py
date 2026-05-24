"""Micro-benchmarks for :class:`~rath.backend.local.LocalBackend.dispatch`.

Establishes a baseline for per-call dispatch overhead on the public sync
facade (which routes through ``runtime().run(_adispatch(...))``). Two
shapes are measured:

- **single**: one ``files.read`` per benchmark iteration.
- **fanout**: N concurrent ``files.read`` calls per iteration (driven from
  a ``ThreadPoolExecutor`` so the sync facade is exercised exactly like a
  user calling it from multiple threads).

Real filesystem, real backend — no mocks. The intent is to flag
regressions, not to publish absolute numbers; pytest-benchmark's own
stats file (``--benchmark-json=...``) carries the data.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from rath.backend import BackendToolFilesRead, BackendToolFilesWrite
from rath.backend.local import LocalBackend

pytestmark = pytest.mark.bench


@pytest.fixture(scope="module")
def _local_sandbox(tmp_path_factory: pytest.TempPathFactory) -> Any:
    backend = LocalBackend()
    sb = backend.open()
    # Seed a small file once so the read benchmark hits a warm path.
    target = "_bench_probe.txt"
    sb.dispatch(BackendToolFilesWrite(path=target, data=b"bench payload\n"))
    try:
        yield sb, target
    finally:
        backend.close(sb)


def test_bench_local_read_single(benchmark: Any, _local_sandbox: Any) -> None:
    sb, target = _local_sandbox
    call = BackendToolFilesRead(path=target)

    def _one() -> None:
        sb.dispatch(call)

    benchmark(_one)


@pytest.mark.parametrize("workers", [1, 4, 16])
def test_bench_local_read_fanout(
    benchmark: Any, _local_sandbox: Any, workers: int
) -> None:
    sb, target = _local_sandbox
    call = BackendToolFilesRead(path=target)

    pool = ThreadPoolExecutor(max_workers=workers)

    def _fanout() -> None:
        futs = [pool.submit(sb.dispatch, call) for _ in range(workers)]
        for f in futs:
            f.result()

    try:
        benchmark(_fanout)
    finally:
        pool.shutdown(wait=True)
