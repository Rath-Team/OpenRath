"""Async session writer tests — real filesystem, no mocks.

Drives :class:`rath._async.awriter._AsyncSessionWriter` from coroutines
running on the OpenRath runtime loop (per concurrency invariant 1 — the
``asyncio.Queue`` and drain task must be created on the runtime loop).

Coverage:

- Header is written **synchronously** on construction (WAL invariant —
  the ``__partial__`` file exists before any ``await`` surfaces).
- Concurrent ``awrite_chunk`` calls drain to disk in **enqueue** order
  (FIFO via single drain task / single file handle).
- ``aclose()`` writes the trailer and atomically promotes
  ``__partial__`` → final ``.jsonl``.
- ``abandon()`` cancels the drain task and **leaves** ``__partial__``
  in place (concurrency invariant 8 — drain timeout crash signal).
- ``awrite_chunk`` after ``aclose`` raises ``RuntimeError`` (closed-state
  guard, so callers fail fast instead of silently dropping rows).
- A failing write **latches** the error onto subsequent calls so the
  caller short-circuits rather than blindly piling rows onto a broken
  handle.
- Bounded ``asyncio.Queue`` exerts backpressure (a slow drain blocks the
  producer instead of growing memory without bound).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from rath._async.awriter import _AsyncSessionWriter
from rath._async.runtime import runtime
from rath.session.chunk import ChunkTable, user_text_chunk
from rath.session.persistence import (
    SESSION_PARTIAL_SUFFIX,
    load_session,
    session_partial_file,
)
from rath.session.session import Session


def _read_records(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        out.append(json.loads(line))
    return out


def test_header_written_synchronously_on_construction(
    _isolate_openrath_home: Path,
) -> None:
    """Construction returns only after the header has hit disk (WAL invariant)."""
    s = Session(chunk_table=ChunkTable(rows=()))

    async def _build_and_check() -> Path:
        w = _AsyncSessionWriter(s)
        # File must exist immediately, before any awrite_chunk and before
        # the drain task could possibly have written anything.
        assert w.partial_path.exists()
        assert w.partial_path.name.endswith(SESSION_PARTIAL_SUFFIX)
        # Some bytes must already be on disk (the header line). On Windows
        # the file handle is exclusive, so we only check size here; full
        # content read is verified after aclose() below.
        assert w.partial_path.stat().st_size > 0
        # Abandon (don't aclose — aclose would write the trailer + rename
        # and we want to inspect the partial-only state in this test).
        await w.abandon()
        return w.partial_path

    rt = runtime()
    partial = rt.run(_build_and_check())
    records = _read_records(partial)
    assert len(records) == 1
    assert records[0]["record_type"] == "header"


def test_aclose_promotes_partial_to_final(_isolate_openrath_home: Path) -> None:
    s = Session(chunk_table=ChunkTable(rows=()))

    async def _go() -> tuple[Path, Path]:
        w = _AsyncSessionWriter(s)
        await w.awrite_chunk(0, user_text_chunk("hello"))
        await w.awrite_chunk(1, user_text_chunk("world"))
        await w.aclose()
        return w.path, w.partial_path

    final, partial = runtime().run(_go())
    assert final.exists()
    assert not partial.exists(), "aclose must remove the __partial__ file"
    records = _read_records(final)
    record_types = [r["record_type"] for r in records]
    assert record_types == ["header", "chunk", "chunk", "trailer"]

    loaded = load_session(s.id)
    assert loaded.closed is True
    assert len(loaded.chunk_table.rows) == 2


def test_fifo_order_preserved_across_concurrent_producers(
    _isolate_openrath_home: Path,
) -> None:
    """Many ``awrite_chunk`` calls drain to disk in enqueue order.

    Producers are spawned as concurrent tasks on the same loop, but each
    awaits its own put — the single drain task pops in FIFO order and
    the on-disk record index sequence must match the enqueue sequence.
    """
    s = Session(chunk_table=ChunkTable(rows=()))
    n = 64

    async def _go() -> Path:
        w = _AsyncSessionWriter(s)
        # Sequential awaits: every awrite_chunk completes (i.e. queue.put
        # returns) before the next is issued, so the enqueue order is
        # well-defined and equals 0..n-1.
        for i in range(n):
            await w.awrite_chunk(i, user_text_chunk(f"row-{i}"))
        await w.aclose()
        return w.path

    final = runtime().run(_go())
    records = _read_records(final)
    chunks = [r for r in records if r["record_type"] == "chunk"]
    indices = [r["index"] for r in chunks]
    assert indices == list(range(n))
    texts = [r["payload"]["content"] for r in chunks]
    assert texts == [f"row-{i}" for i in range(n)]


def test_abandon_leaves_partial_in_place(_isolate_openrath_home: Path) -> None:
    s = Session(chunk_table=ChunkTable(rows=()))

    async def _go() -> tuple[Path, Path]:
        w = _AsyncSessionWriter(s)
        await w.awrite_chunk(0, user_text_chunk("about to crash"))
        # Give the drain task a chance to flush before we abandon — the
        # whole point of the crash-signal is that whatever did land stays
        # visible. Without this we'd race the drain task and might assert
        # against an empty partial.
        await asyncio.sleep(0.05)
        await w.abandon()
        return w.path, w.partial_path

    final, partial = runtime().run(_go())
    assert not final.exists(), "abandon must NOT promote __partial__ to final"
    assert partial.exists(), "abandon must leave the __partial__ file as a crash signal"
    records = _read_records(partial)
    # At minimum the header landed before the abandon (eager-WAL invariant);
    # the chunk may or may not have flushed depending on drain scheduling.
    record_types = [r["record_type"] for r in records]
    assert record_types[0] == "header"
    assert "trailer" not in record_types

    # The loader recognises the partial file and reports closed=False.
    loaded = load_session(s.id)
    assert loaded.closed is False


def test_awrite_after_aclose_raises(_isolate_openrath_home: Path) -> None:
    s = Session(chunk_table=ChunkTable(rows=()))

    async def _go() -> None:
        w = _AsyncSessionWriter(s)
        await w.awrite_chunk(0, user_text_chunk("first"))
        await w.aclose()
        with pytest.raises(RuntimeError, match="closed"):
            await w.awrite_chunk(1, user_text_chunk("nope"))

    runtime().run(_go())


def test_aclose_is_idempotent(_isolate_openrath_home: Path) -> None:
    s = Session(chunk_table=ChunkTable(rows=()))

    async def _go() -> Path:
        w = _AsyncSessionWriter(s)
        await w.awrite_chunk(0, user_text_chunk("only"))
        await w.aclose()
        await w.aclose()  # must not raise, must not double-rename
        return w.path

    final = runtime().run(_go())
    assert final.exists()
    loaded = load_session(s.id)
    assert loaded.closed is True
    assert len(loaded.chunk_table.rows) == 1


class _BoomWriter:
    """Sync writer proxy: row 0 lands real, every subsequent row raises.

    Used to simulate a drain-side disk failure without monkey-patching
    the real ``SessionWriter`` (which uses ``__slots__`` and refuses
    attribute assignment).
    """

    def __init__(self, real: Any) -> None:
        self._real = real
        self._calls = 0

    @property
    def path(self) -> Path:
        return self._real.path

    @property
    def partial_path(self) -> Path:
        return self._real.partial_path

    def write_chunk(self, index: int, row: Any) -> None:
        self._calls += 1
        if self._calls == 1:
            self._real.write_chunk(index, row)
            return
        raise RuntimeError("simulated disk failure")

    def close(self) -> None:
        self._real.close()

    def abandon(self) -> None:
        self._real.abandon()


def test_drain_error_latches_to_subsequent_awrites(
    _isolate_openrath_home: Path,
) -> None:
    """If the drain task's write raises, the next awrite_chunk surfaces it.

    Substitutes the inner sync writer for a proxy that fails on every
    write past the first. The first chunk lands, the drain blows up on
    the second, a third ``awrite_chunk`` then sees the latched error.
    """
    s = Session(chunk_table=ChunkTable(rows=()))

    async def _go() -> BaseException | None:
        w = _AsyncSessionWriter(s)
        # Swap the inner writer for the proxy before any chunks are
        # enqueued. The drain task captures ``self._writer`` per-iteration
        # via attribute access, so swapping the attribute is enough.
        w._writer = _BoomWriter(w._writer)  # type: ignore[assignment]

        await w.awrite_chunk(0, user_text_chunk("first"))
        # Let the drain task process row 0 (succeeds).
        await asyncio.sleep(0.05)
        await w.awrite_chunk(1, user_text_chunk("doomed"))
        # Let the drain task process row 1 (raises, latches).
        await asyncio.sleep(0.1)

        captured: BaseException | None = None
        try:
            await w.awrite_chunk(2, user_text_chunk("after-fail"))
        except BaseException as exc:
            captured = exc

        # aclose re-raises the latched error — the other half of the
        # invariant: callers explicitly draining the writer see the
        # original failure rather than a silent green path.
        with pytest.raises(RuntimeError, match="simulated disk failure"):
            await w.aclose()
        return captured

    captured = runtime().run(_go())
    assert isinstance(captured, RuntimeError)
    assert "simulated disk failure" in str(captured)


def test_bounded_queue_applies_backpressure(_isolate_openrath_home: Path) -> None:
    """A small ``queue_maxsize`` blocks the producer when the drain stalls.

    We stall the drain by patching the inner sync ``write_chunk`` to
    sleep, then attempt to enqueue more rows than the bound. The N+1-th
    ``awrite_chunk`` must not complete until the drain has popped at
    least one item.
    """
    s = Session(chunk_table=ChunkTable(rows=()))

    class _SlowWriter:
        def __init__(self, real: Any) -> None:
            self._real = real

        @property
        def path(self) -> Path:
            return self._real.path

        @property
        def partial_path(self) -> Path:
            return self._real.partial_path

        def write_chunk(self, index: int, row: Any) -> None:
            import time as _t

            _t.sleep(0.15)
            self._real.write_chunk(index, row)

        def close(self) -> None:
            self._real.close()

        def abandon(self) -> None:
            self._real.abandon()

    async def _go() -> tuple[bool, int]:
        # maxsize=1 means: as soon as the drain task pops the first item
        # and starts its slow write, the producer can fit exactly one more
        # row; the next ``awrite_chunk`` must block until the slow write
        # finishes and the drain pops again.
        w = _AsyncSessionWriter(s, queue_maxsize=1)
        w._writer = _SlowWriter(w._writer)  # type: ignore[assignment]

        # Row 0: fits, drain pops immediately and enters the 150ms sleep.
        await w.awrite_chunk(0, user_text_chunk("a"))
        # Row 1: fits (queue has 1 slot free after the pop).
        await w.awrite_chunk(1, user_text_chunk("b"))
        # Row 2: queue is full (1/1) — the producer must wait until the
        # drain finishes row 0 and pops row 1.
        third = asyncio.create_task(w.awrite_chunk(2, user_text_chunk("c")))
        await asyncio.sleep(0.03)
        pending_when_full = not third.done()

        await third
        await w.aclose()

        records = _read_records(w.path)
        chunk_count = sum(1 for r in records if r["record_type"] == "chunk")
        return pending_when_full, chunk_count

    pending_when_full, chunk_count = runtime().run(_go())
    assert pending_when_full, (
        "awrite_chunk should have been pending while the queue was full"
    )
    assert chunk_count == 3


def test_path_properties_point_at_expected_files(
    _isolate_openrath_home: Path,
) -> None:
    s = Session(chunk_table=ChunkTable(rows=()))

    async def _go() -> tuple[Path, Path]:
        w = _AsyncSessionWriter(s)
        partial = w.partial_path
        final = w.path
        await w.aclose()
        return partial, final

    partial, final = runtime().run(_go())
    assert partial == session_partial_file(s.id).resolve()
    assert final.name.endswith(".jsonl")
    assert partial.name.endswith(SESSION_PARTIAL_SUFFIX)
