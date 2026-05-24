"""Persistent identity for memory stores.

Memory-plane parallel to :mod:`rath.backend.persistence`. Today this covers
the **local** memory backend: each store gets a stable directory under
``.openrath/memory/local/<uuid>/`` that survives ``close()`` and can be
reopened by the same id in a later process.

A future ``openviking`` mirror — JSON records pinning a remote OpenViking
store id — would live under ``.openrath/memory/openviking/`` and is not
yet implemented.
"""

from rath.memory.persistence.paths import (
    LOCAL_SUBDIR,
    MEMORY_DIR_NAME,
    ensure_local_memory_root,
    local_memory_root,
    local_store_dir,
    memory_root,
)
from rath.memory.persistence.registry import PersistentMemoryRegistry

__all__ = [
    "PersistentMemoryRegistry",
    "MEMORY_DIR_NAME",
    "LOCAL_SUBDIR",
    "memory_root",
    "local_memory_root",
    "local_store_dir",
    "ensure_local_memory_root",
]
