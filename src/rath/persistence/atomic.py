"""Atomic file writes shared across the persistence planes.

Writing config, registry, and memory sidecar files with a bare
``path.write_text(...)`` has two problems:

1. **Not atomic** — a crash or exception mid-write leaves a truncated file
   that later fails to parse.
2. **Not concurrency-safe on Windows** — even the temp-file + ``os.replace``
   idiom raises :class:`PermissionError` when a second thread/process holds
   the destination open during the replace, because Windows rejects a rename
   onto an open file for a brief sharing window.

:func:`atomic_write_text` / :func:`atomic_write_json` solve both: they write
to a uniquely-named temp file in the target directory, ``os.replace`` it into
place (atomic on POSIX and Windows), serialize concurrent writers to the same
path through a process-global path-keyed lock, and retry the short Windows
sharing-violation window before giving up.

These are process-local guarantees. Cross-*process* exclusion for
append-style writers is a separate concern handled by
:class:`rath.session.persistence._lock.FileLock`.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

__all__ = ["atomic_write_text", "atomic_write_json"]

# Process-global, path-keyed locks so two ConfigStore/registry instances that
# point at the same file cannot race their os.replace calls. Keyed by the
# resolved target path. The registry itself is guarded by ``_LOCKS_GUARD``.
_LOCKS: dict[Path, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()

# Windows only: os.replace onto a concurrently-held target raises
# PermissionError for a brief window. Retry a handful of times with a short
# backoff before surfacing the error.
_WIN_REPLACE_ATTEMPTS = 10
_WIN_REPLACE_BACKOFF_S = 0.02


def _lock_for(path: Path) -> threading.Lock:
    with _LOCKS_GUARD:
        lock = _LOCKS.get(path)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[path] = lock
        return lock


def _replace_with_retry(src: Path, dst: Path) -> None:
    """``os.replace(src, dst)`` with a Windows sharing-violation retry loop."""
    if not sys.platform.startswith("win"):
        os.replace(src, dst)
        return
    last: OSError | None = None
    for attempt in range(_WIN_REPLACE_ATTEMPTS):
        try:
            os.replace(src, dst)
            return
        except PermissionError as e:  # target briefly held by another writer
            last = e
            time.sleep(_WIN_REPLACE_BACKOFF_S * (attempt + 1))
    assert last is not None
    raise last


def atomic_write_text(
    path: Path | str,
    text: str,
    *,
    newline: bool = False,
    encoding: str = "utf-8",
    mode: int | None = None,
) -> None:
    """Atomically write ``text`` to ``path``.

    Creates the parent directory if missing. Writes a uniquely-named temp
    file in the same directory, then ``os.replace`` it into place. Concurrent
    writers to the same resolved path are serialized; the Windows
    sharing-violation window is retried. On any failure the temp file is
    removed and the original target is left untouched.

    ``newline`` appends a trailing ``"\\n"`` when the caller has not already.
    ``mode`` (e.g. ``0o600``) restricts the final file on POSIX; ignored on
    Windows (matching :func:`rath.config.secrets.chmod_user_only`).
    """
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if newline and not text.endswith("\n"):
        text = text + "\n"

    lock = _lock_for(target)
    with lock:
        fd = tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            dir=target.parent,
            prefix=".atomic_",
            suffix=".tmp",
            delete=False,
        )
        tmp_path = Path(fd.name)
        try:
            fd.write(text)
            fd.flush()
            os.fsync(fd.fileno())
            fd.close()
            _replace_with_retry(tmp_path, target)
        except BaseException:
            try:
                fd.close()
            except Exception:  # noqa: BLE001 -- already closing down
                pass
            tmp_path.unlink(missing_ok=True)
            raise
        if mode is not None and not sys.platform.startswith("win"):
            try:
                os.chmod(target, mode)
            except OSError:  # pragma: no cover -- racing fs / unsupported
                pass


def atomic_write_json(
    path: Path | str,
    payload: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = False,
    ensure_ascii: bool = False,
    mode: int | None = None,
) -> None:
    """Atomically write ``payload`` as JSON to ``path``.

    Serialization happens **before** the temp file is created, so an
    unserializable payload raises without touching the filesystem (no temp
    debris, original target intact). Otherwise defers to
    :func:`atomic_write_text`.
    """
    text = json.dumps(
        payload, indent=indent, sort_keys=sort_keys, ensure_ascii=ensure_ascii
    )
    atomic_write_text(path, text, newline=True, mode=mode)
