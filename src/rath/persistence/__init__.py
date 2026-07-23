"""Cross-cutting persistence helpers shared by the session, backend, and
memory planes.

The one public primitive today is the atomic-write helper
(:func:`~rath.persistence.atomic.atomic_write_text` /
:func:`~rath.persistence.atomic.atomic_write_json`): a temp-file +
``os.replace`` writer that is durable on POSIX and Windows and safe under
concurrent writers to the same path.
"""

from __future__ import annotations

from rath.persistence.atomic import atomic_write_json, atomic_write_text
from rath.persistence.errors import PersistenceError
from rath.persistence.gc import GCReport, gc
from rath.persistence.jsonl import (
    JsonlAppendWriter,
    dumps_jsonl,
    iter_jsonl,
    write_jsonl,
)
from rath.persistence.lock import FileLock
from rath.persistence.manifest import (
    LAYOUT_VERSION,
    ManifestVersionError,
    check_manifest,
    ensure_manifest,
)

__all__ = [
    "atomic_write_text",
    "dumps_jsonl",
    "FileLock",
    "atomic_write_json",
    "gc",
    "GCReport",
    "ensure_manifest",
    "check_manifest",
    "ManifestVersionError",
    "LAYOUT_VERSION",
    "iter_jsonl",
    "JsonlAppendWriter",
    "PersistenceError",
    "write_jsonl",
]
