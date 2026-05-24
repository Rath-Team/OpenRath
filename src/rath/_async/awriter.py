"""Async session writer with a FIFO drain task.

Runtime-internal counterpart of :class:`~rath.session.persistence.SessionWriter`.
The session-loop coroutine never touches the filesystem directly — it
``await``s :meth:`_AsyncSessionWriter.awrite_chunk`, which enqueues the
``(index, row)`` onto a bounded :class:`asyncio.Queue` and returns
immediately after the queue accepts the item. A single background drain
task pops items in order and writes them via :func:`asyncio.to_thread` so
slow flushes never park the runtime loop.

Properties relied on by the runtime:

- FIFO ordering — a single drain task with a single open file handle.
- Strict header-first — the underlying :class:`SessionWriter` writes its
  header in ``__init__`` (WAL), so a crash before the first chunk still
  leaves a visible ``__partial__`` file with a parseable header.
- Backpressure — the queue is bounded (``maxsize=256``); a producer that
  outruns the disk awaits queue capacity instead of growing memory
  without bound.
- ``aclose()`` — drains the queue, writes the trailer, atomically
  renames the ``__partial__`` file to its final ``.jsonl`` name.
- ``abandon()`` — cancels the drain task, releases the handle, and
  leaves the ``__partial__`` file in place (concurrency invariant 8).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from rath.session.chunk import ChunkRow
from rath.session.persistence import SessionWriter
from rath.session.session import Session

__all__ = ["_AsyncSessionWriter"]

logger = logging.getLogger(__name__)


_SENTINEL: Any = object()


class _AsyncSessionWriter:
    """Async-facing wrapper around :class:`SessionWriter` with a FIFO drain.

    Construction is synchronous (header writes immediately to disk —
    invariant: header lands before any awaitable surfaces). After that
    every write goes through an :class:`asyncio.Queue`; a single drain
    task pops items and dispatches the actual ``write_chunk`` call to a
    worker thread.
    """

    __slots__ = (
        "_writer",
        "_queue",
        "_drain_task",
        "_closed",
        "_error",
    )

    def __init__(
        self,
        session: Session,
        *,
        sandbox_handle_id: str | None = None,
        path: Path | None = None,
        queue_maxsize: int = 256,
    ) -> None:
        # WAL: writing the header here means a crash between construction
        # and the first awrite_chunk still leaves the partial file behind.
        self._writer = SessionWriter(
            session, sandbox_handle_id=sandbox_handle_id, path=path
        )
        self._queue: asyncio.Queue[tuple[int, ChunkRow] | object] = asyncio.Queue(
            maxsize=queue_maxsize
        )
        self._closed = False
        self._error: BaseException | None = None
        # Drain task is spawned on the runtime loop. Must be created from a
        # running loop — ``_AsyncSessionWriter`` is always built inside
        # ``_arun_session_loop`` so that's guaranteed.
        self._drain_task: asyncio.Task[None] = asyncio.create_task(
            self._drain(), name=f"session-writer-{session.id}"
        )

    @property
    def path(self) -> Path:
        """The final on-disk path (after :meth:`aclose`)."""
        return self._writer.path

    @property
    def partial_path(self) -> Path:
        """The in-flight ``__partial__`` path."""
        return self._writer.partial_path

    async def awrite_chunk(self, index: int, row: ChunkRow) -> None:
        """Enqueue one chunk for asynchronous writing.

        Awaits queue capacity (backpressure). Raises whatever the drain
        task surfaced from a prior write — the first failure latches and
        propagates to subsequent calls so the caller can short-circuit.
        """
        if self._error is not None:
            raise self._error
        if self._closed:
            raise RuntimeError(
                "_AsyncSessionWriter is closed; cannot enqueue more chunks"
            )
        await self._queue.put((index, row))

    async def aclose(self) -> None:
        """Drain pending writes, emit trailer, atomically rename to final path.

        Idempotent. If the drain task already failed, re-raises the
        original error after best-effort cleanup so callers can observe
        it.
        """
        if self._closed:
            return
        self._closed = True
        # Signal the drain task to exit. The sentinel races with any
        # queued (index, row) tuples; ordering is preserved because the
        # queue is FIFO.
        await self._queue.put(_SENTINEL)
        try:
            await self._drain_task
        except asyncio.CancelledError:
            # Cancellation here means abandon() ran concurrently; the
            # partial file is left in place. Re-raise so the runtime can
            # see we were cancelled.
            raise
        # ``close()`` writes the trailer and renames partial → final.
        # Run in a worker thread to keep the loop responsive on slow fs.
        await asyncio.to_thread(self._writer.close)
        if self._error is not None:
            raise self._error

    async def abandon(self) -> None:
        """Cancel the drain task and leave ``__partial__`` on disk as a crash signal.

        Used when the runtime's :meth:`drain` budget is exhausted
        (concurrency invariant 8) — no trailer, no rename.
        """
        if self._closed:
            return
        self._closed = True
        self._drain_task.cancel()
        try:
            await self._drain_task
        except (asyncio.CancelledError, Exception):
            pass
        await asyncio.to_thread(self._writer.abandon)

    # ---------------------------------------------------------------- internals

    async def _drain(self) -> None:
        """Pop chunks in order and write them to disk.

        Single-consumer task — the only one allowed to touch
        ``self._writer.write_chunk``. ``asyncio.to_thread`` is used per
        write so a slow disk flush never blocks the runtime loop.
        """
        try:
            while True:
                item = await self._queue.get()
                if item is _SENTINEL:
                    return
                index, row = item  # type: ignore[misc]
                try:
                    await asyncio.to_thread(self._writer.write_chunk, index, row)
                except asyncio.CancelledError:
                    # abandon() is asking us to stop; propagate so the
                    # outer handler runs and the awaiter unblocks.
                    raise
                except Exception as exc:
                    # Latch the error so awrite_chunk / aclose surface it.
                    # Continue draining to avoid leaking queue items, but
                    # skip the actual file write — once a write has failed
                    # the file integrity is already in doubt.
                    self._error = exc
                    logger.exception(
                        "async session writer drain failed; subsequent chunks dropped"
                    )
        except asyncio.CancelledError:
            # Propagate so aclose / abandon can observe cancellation.
            raise
