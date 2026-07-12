"""Cross-process advisory lock for cooperating append writers."""

from __future__ import annotations

import sys
from typing import IO

from rath.persistence.errors import PersistenceError

__all__ = ["FileLock"]


class FileLock:
    """Acquire an exclusive non-blocking lock on a file descriptor."""

    __slots__ = ("_fp", "_acquired")

    def __init__(self, fp: IO[str]) -> None:
        self._fp = fp
        self._acquired = False

    def acquire(self) -> None:
        if self._acquired:
            return
        try:
            self._platform_acquire()
        except OSError as exc:
            raise PersistenceError(
                f"another process is already writing to {self._fp.name!r}; "
                "refusing to interleave appends"
            ) from exc
        self._acquired = True

    def release(self) -> None:
        if not self._acquired:
            return
        try:
            self._platform_release()
        except OSError:
            pass
        self._acquired = False

    def _platform_acquire(self) -> None:
        if sys.platform.startswith("win"):
            import msvcrt  # type: ignore[import-not-found, unused-ignore]

            saved = self._fp.tell()
            try:
                self._fp.seek(0)
                msvcrt.locking(self._fp.fileno(), msvcrt.LK_NBLCK, 1)
            finally:
                self._fp.seek(saved)
        else:
            import fcntl

            fcntl.flock(self._fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _platform_release(self) -> None:
        if sys.platform.startswith("win"):
            import msvcrt  # type: ignore[import-not-found, unused-ignore]

            saved = self._fp.tell()
            try:
                self._fp.seek(0)
                msvcrt.locking(self._fp.fileno(), msvcrt.LK_UNLCK, 1)
            finally:
                self._fp.seek(saved)
        else:
            import fcntl

            fcntl.flock(self._fp.fileno(), fcntl.LOCK_UN)
