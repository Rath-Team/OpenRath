"""Strict JSONL encoding, reading, atomic overwrite, and locked append."""

from __future__ import annotations

import json
import os
import sys
import threading
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from rath.persistence.atomic import atomic_write_text
from rath.persistence.lock import FileLock

__all__ = ["JsonlAppendWriter", "dumps_jsonl", "iter_jsonl", "write_jsonl"]

_APPEND_LOCKS_GUARD = threading.Lock()
_APPEND_LOCKS: dict[Path, threading.Lock] = {}


def _append_lock_for(path: Path) -> threading.Lock:
    with _APPEND_LOCKS_GUARD:
        lock = _APPEND_LOCKS.get(path)
        if lock is None:
            lock = threading.Lock()
            _APPEND_LOCKS[path] = lock
        return lock


def dumps_jsonl(records: Iterable[Mapping[str, Any]]) -> str:
    """Serialize mappings as strict one-object-per-line JSON."""

    lines: list[str] = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, Mapping):
            raise TypeError(f"JSONL record {index} must be a mapping")
        lines.append(
            json.dumps(
                dict(record),
                ensure_ascii=False,
                sort_keys=False,
                allow_nan=False,
            )
        )
    return "" if not lines else "\n".join(lines) + "\n"


class JsonlAppendWriter:
    """Hold process and file locks across a sequence of JSONL appends."""

    __slots__ = ("path", "_process_lock", "_handle", "_file_lock", "_closed")

    def __init__(self, path: str | Path, *, mode: int | None = None) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.exists()
        self._process_lock = _append_lock_for(self.path)
        self._process_lock.acquire()
        self._handle = None
        self._file_lock = None
        self._closed = False
        try:
            self._handle = self.path.open("a+", encoding="utf-8")
            self._file_lock = FileLock(self._handle)
            self._file_lock.acquire()
            if mode is not None and not existed and not sys.platform.startswith("win"):
                os.chmod(self.path, mode)
        except BaseException:
            if self._handle is not None:
                self._handle.close()
            self._process_lock.release()
            self._closed = True
            raise

    def append(self, records: Iterable[Mapping[str, Any]]) -> None:
        if self._closed:
            raise RuntimeError(f"JsonlAppendWriter({self.path}) is closed")
        text = dumps_jsonl(records)
        assert self._handle is not None
        self._handle.write(text)
        self._handle.flush()

    def close(self) -> None:
        if self._closed:
            return
        try:
            if self._file_lock is not None:
                self._file_lock.release()
            if self._handle is not None:
                self._handle.close()
        finally:
            self._closed = True
            self._process_lock.release()

    def __enter__(self) -> "JsonlAppendWriter":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def iter_jsonl(path: str | Path) -> Iterator[tuple[int, dict[str, Any]]]:
    """Yield ``(line_number, object)`` records with strict diagnostics."""

    target = Path(path)
    try:
        with target.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"{target}:{line_number}: invalid JSON: {exc.msg}"
                    ) from exc
                if not isinstance(value, dict):
                    raise ValueError(
                        f"{target}:{line_number}: JSONL record must be an object"
                    )
                yield line_number, value
    except OSError as exc:
        raise OSError(f"failed to read JSONL file {target}: {exc}") from exc


def write_jsonl(
    path: str | Path,
    records: Iterable[Mapping[str, Any]],
    *,
    append: bool = False,
    mode: int | None = None,
) -> None:
    """Write a fully serialized JSONL batch atomically or under an append lock."""

    text = dumps_jsonl(records)
    target = Path(path).resolve()
    if not append:
        atomic_write_text(target, text, mode=mode)
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    process_lock = _append_lock_for(target)
    with process_lock:
        existed = target.exists()
        with target.open("a+", encoding="utf-8") as handle:
            lock = FileLock(handle)
            lock.acquire()
            try:
                handle.write(text)
                handle.flush()
            finally:
                lock.release()
        if mode is not None and not existed and not sys.platform.startswith("win"):
            os.chmod(target, mode)
