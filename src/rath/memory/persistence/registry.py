"""Process-independent registry of persisted memory stores.

:class:`PersistentMemoryRegistry` maps UUIDs to stable on-disk directories
under ``.openrath/memory/local/<uuid>/`` for :class:`LocalMemoryBackend`
reuse. Mirrors :class:`rath.backend.persistence.PersistentSandboxRegistry`,
local half only — remote (OpenViking) records are not tracked here yet.

The registry holds no live :class:`MemoryStore` handles; it only tracks
identity so subsequent processes can reopen a store with the same id.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from rath.memory.persistence.paths import (
    local_memory_root,
    local_store_dir,
)

__all__ = ["PersistentMemoryRegistry"]

logger = logging.getLogger(__name__)


class PersistentMemoryRegistry:
    """Filesystem-backed registry of persisted local memory store identities.

    Instances are cheap; everything lives on disk under
    ``.openrath/memory/local/``. The class does **no** locking; callers
    that share a registry across threads should serialize writes externally.
    """

    def alloc_local_id(self) -> UUID:
        """Generate a new UUID and create its store directory.

        Returns the UUID. Use :meth:`local_path` to resolve it back to a
        :class:`pathlib.Path`.
        """
        sid = uuid4()
        target = local_store_dir(sid)
        target.mkdir(parents=True, exist_ok=True)
        return sid

    def ensure_local(self, store_id: UUID | str) -> Path:
        """Create the directory for ``store_id`` if missing; return it.

        Idempotent — useful when the caller already knows the id from a
        persisted handle and wants to rebind the same store.
        """
        target = local_store_dir(store_id)
        target.mkdir(parents=True, exist_ok=True)
        return target

    def local_path(self, store_id: UUID | str) -> Path:
        """Resolve a store id to its on-disk directory.

        Does not check existence — use :meth:`ensure_local` to create on
        demand. Returns the path even when the directory has been removed
        so callers can decide whether to recreate.
        """
        return local_store_dir(store_id)

    def list_local(self) -> list[UUID]:
        """Enumerate UUID-named subdirectories under ``memory/local/``."""
        root = local_memory_root()
        if not root.is_dir():
            return []
        ids: list[UUID] = []
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            try:
                ids.append(UUID(entry.name))
            except ValueError:
                logger.debug("ignoring non-UUID dir in local memory: %s", entry)
        return ids

    def delete_local(self, store_id: UUID | str) -> bool:
        """Remove the on-disk directory for a local store.

        Returns ``True`` when the directory existed and was removed,
        ``False`` when it was already absent. Idempotent.
        """
        path = local_store_dir(store_id)
        if not path.exists():
            return False
        shutil.rmtree(path, ignore_errors=False)
        return True

    def prune_local(self, *, older_than: timedelta) -> list[UUID]:
        """Remove local stores whose mtime is older than ``older_than``.

        Returns the list of removed ids in deletion order.
        """
        cutoff = datetime.now(timezone.utc) - older_than
        removed: list[UUID] = []
        for sid in self.list_local():
            path = local_store_dir(sid)
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if mtime < cutoff and self.delete_local(sid):
                removed.append(sid)
        return removed
