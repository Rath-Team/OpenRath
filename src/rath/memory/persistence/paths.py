"""Filesystem layout for persisted memory stores.

Shares the resolved ``.openrath/`` root with :mod:`rath.config` and
:mod:`rath.backend.persistence`. Local memory stores get a stable directory
under ``.openrath/memory/local/<uuid>/`` holding the store's full content
(``meta.json`` + per-scope subtrees).

Pure functions: they describe paths and optionally ``mkdir`` the parent.
No content is read or written here.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from rath.config.paths import resolve_config_dir

__all__ = [
    "MEMORY_DIR_NAME",
    "LOCAL_SUBDIR",
    "memory_root",
    "local_memory_root",
    "local_store_dir",
    "ensure_local_memory_root",
]

MEMORY_DIR_NAME = "memory"
LOCAL_SUBDIR = "local"


def memory_root() -> Path:
    """``<resolved-config-dir>/memory`` (not created)."""
    return resolve_config_dir() / MEMORY_DIR_NAME


def local_memory_root() -> Path:
    """``<resolved-config-dir>/memory/local`` (not created)."""
    return memory_root() / LOCAL_SUBDIR


def local_store_dir(store_id: UUID | str) -> Path:
    """``<local_memory_root>/<store_id>`` — the per-store directory."""
    return local_memory_root() / str(store_id)


def ensure_local_memory_root() -> Path:
    """Create ``memory/local/`` (and parents) if missing; return the path."""
    target = local_memory_root()
    target.mkdir(parents=True, exist_ok=True)
    return target
