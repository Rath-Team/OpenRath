"""Append-only WAL writer for one persisted session file.

A :class:`SessionWriter` owns the file handle for
``<sessions>/<id>.jsonl.__partial__`` during the lifetime of one session.
The header is written **immediately on construction** so a crash before the
first chunk still leaves a durable, machine-recognizable in-flight file.
Each subsequent chunk is serialized as one line,
``json.dumps(..., ensure_ascii=False)`` + ``"\\n"``, followed by ``flush()``
so a ``kill -9`` loses at most the last partial line.

``close()`` writes a ``record_type=trailer`` line carrying the final chunk
count and cumulative usage, then atomically renames the ``__partial__``
file to ``<id>.jsonl`` — the rename is the durable "session closed
cleanly" signal. A surviving ``__partial__`` file is the crash signal.
``abandon()`` releases the handle but leaves the ``__partial__`` file in
place so operators can see what was lost.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from types import TracebackType
from typing import IO, Any

from rath.config.secrets import chmod_user_only
from rath.session.chunk import ChunkRow
from rath.session.persistence._lock import FileLock
from rath.session.persistence._serialize import (
    build_chunk_record,
    build_header,
    build_trailer,
)
from rath.session.persistence.paths import (
    ensure_sessions_dir,
    session_file,
    session_partial_file,
)
from rath.session.session import Session

__all__ = ["SessionWriter"]

logger = logging.getLogger(__name__)


class SessionWriter:
    """Append-only JSONL WAL writer for one :class:`~rath.session.session.Session`.

    Usage::

        writer = SessionWriter(session)        # opens <id>.jsonl.__partial__,
                                               # writes header immediately
        writer.write_chunk(0, row_0)
        writer.write_chunk(1, row_1)
        ...
        writer.close()                          # writes trailer, renames to
                                                # <id>.jsonl atomically

    The writer can also be used as a context manager — ``__exit__`` calls
    :meth:`close` when no exception is in flight and :meth:`abandon`
    otherwise (so a crash midway leaves the ``__partial__`` file behind,
    marking the session as ``closed=False`` on reload).
    """

    __slots__ = (
        "_session",
        "_final_path",
        "_partial_path",
        "_sandbox_handle_id",
        "_file",
        "_lock",
        "_chunks_written",
        "_closed",
    )

    def __init__(
        self,
        session: Session,
        *,
        sandbox_handle_id: str | None = None,
        path: Path | None = None,
    ) -> None:
        self._session = session
        if path is not None:
            final_path = path.resolve()
            partial_path = final_path.with_name(final_path.name + ".__partial__")
        else:
            final_path = session_file(session.id).resolve()
            partial_path = session_partial_file(session.id).resolve()
        self._final_path = final_path
        self._partial_path = partial_path
        self._sandbox_handle_id = sandbox_handle_id
        self._file: IO[str] | None = None
        self._lock: FileLock | None = None
        self._chunks_written = 0
        self._closed = False
        # WAL: open and write the header now. Any failure here propagates
        # before the writer is ever observed, so we never see a "writer
        # exists but no file" state once construction returns.
        self._open()
        self._write_record(
            build_header(self._session, sandbox_handle_id=self._sandbox_handle_id)
        )

    @property
    def path(self) -> Path:
        """Absolute path to the on-disk JSONL file after :meth:`close`.

        Note this is the *final* path. While the writer is still in-flight
        the file lives at :attr:`partial_path`; readers that want to look
        at an in-flight session should use that attribute instead.
        """
        return self._final_path

    @property
    def partial_path(self) -> Path:
        """Absolute path to the in-flight ``.__partial__`` file."""
        return self._partial_path

    @property
    def chunks_written(self) -> int:
        """Number of ``record_type=chunk`` lines flushed so far."""
        return self._chunks_written

    # ------------------------------------------------------------------ writes

    def write_chunk(self, index: int, row: ChunkRow) -> None:
        """Append one chunk record."""
        if self._closed:
            raise RuntimeError(
                f"SessionWriter({self._final_path}) is closed; cannot append more chunks",
            )
        self._write_record(build_chunk_record(index, row))
        self._chunks_written += 1

    def close(self) -> None:
        """Write the trailer and atomically rename ``__partial__`` → final.

        Idempotent.
        """
        if self._closed:
            return
        try:
            if self._file is not None:
                self._write_record(
                    build_trailer(
                        self._session,
                        final_chunk_count=self._chunks_written,
                    )
                )
        finally:
            self._release()
            self._closed = True
        # Atomic rename — only happens if trailer wrote successfully and the
        # handle released cleanly. A crash between the trailer write and the
        # rename still leaves a complete-but-still-``__partial__`` file
        # that the loader treats as ``closed=False``; the rename is what
        # promotes "complete content" to "advertised as closed".
        try:
            os.replace(self._partial_path, self._final_path)
        except FileNotFoundError:
            # Partial path is already gone — concurrent operator cleanup or
            # the file was never created (header write failed silently).
            # Either way there's nothing to promote.
            return

    def abandon(self) -> None:
        """Release the file handle WITHOUT writing a trailer or renaming.

        Leaves the ``__partial__`` file in place — a visible signal that
        the writing process crashed mid-session or that the runtime drain
        timed out. The loader still tolerates this file via
        :func:`~rath.session.persistence.loader.load_session`.
        """
        if self._closed:
            return
        self._release()
        self._closed = True

    # ------------------------------------------------------------------ context

    def __enter__(self) -> "SessionWriter":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is None:
            self.close()
        else:
            self.abandon()

    # ------------------------------------------------------------------ internals

    def _open(self) -> None:
        # Ensure the parent directory exists. For the default path this is
        # ``<resolved>/sessions``; for callers that passed an explicit path
        # we still want to ``mkdir -p`` so unit tests / one-off uses don't
        # need to pre-create the directory.
        self._partial_path.parent.mkdir(parents=True, exist_ok=True)
        ensure_sessions_dir()
        existed = self._partial_path.exists()
        self._file = self._partial_path.open("a", encoding="utf-8")
        # Acquire an exclusive advisory lock so a second process opening the
        # same session id fails fast instead of silently interleaving lines.
        self._lock = FileLock(self._file)
        try:
            self._lock.acquire()
        except Exception:
            self._file.close()
            self._file = None
            self._lock = None
            raise
        # Apply 0600 the first time we touch the file. Idempotent on POSIX;
        # no-op on Windows (NTFS uses ACLs).
        if not existed:
            chmod_user_only(self._partial_path)

    def _write_record(self, record: dict[str, Any]) -> None:
        assert self._file is not None
        line = json.dumps(record, ensure_ascii=False, sort_keys=False)
        self._file.write(line + "\n")
        self._file.flush()

    def _release(self) -> None:
        if self._lock is not None:
            self._lock.release()
            self._lock = None
        if self._file is None:
            return
        try:
            self._file.close()
        except OSError:  # pragma: no cover -- racing fs
            logger.exception(
                "failed to close persisted session file %s", self._partial_path
            )
        self._file = None
