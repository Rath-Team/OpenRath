"""Process-independent registry of persisted sandboxes.

:class:`PersistentSandboxRegistry` maps UUIDs to either:

* a stable on-disk working directory under
  ``.openrath/sandboxes/local/<uuid>/`` for :class:`LocalBackend` reuse, or
* a JSON record under ``.openrath/sandboxes/opensandbox/<uuid>.json`` that
  pins an OpenSandbox remote sandbox id for a future reattach (Phase B).

The registry holds no live :class:`BackendSandbox` handles — those remain
process-local. It only tracks the **identity** so subsequent processes can
reopen a sandbox with the same spec / remote id.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from rath.backend.abc import BackendSandbox, BackendSandboxSpec
from rath.backend.persistence.paths import (
    ensure_local_root,
    ensure_opensandbox_root,
    local_root,
    local_sandbox_dir,
    opensandbox_index_path,
    opensandbox_root,
)
from rath.backend.persistence.spec_json import (
    SCHEMA_VERSION,
    spec_from_jsonable,
    spec_to_jsonable,
)
from rath.backend.registry import get as backend_get
from rath.config.secrets import chmod_user_only
from rath.persistence.atomic import atomic_write_json

__all__ = [
    "PersistentSandboxRegistry",
    "RemoteSandboxRecord",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True, slots=True)
class RemoteSandboxRecord:
    """One ``.openrath/sandboxes/opensandbox/<uuid>.json`` decoded."""

    schema_version: int
    id: UUID
    backend: str
    remote_id: str
    spec: BackendSandboxSpec | None
    created_at: datetime
    last_used_at: datetime
    path: Path = field(repr=False)


class PersistentSandboxRegistry:
    """Filesystem-backed registry of persisted sandbox identities.

    Instances are cheap; everything lives on disk under
    ``.openrath/sandboxes/{local,opensandbox}/``. The class does **no**
    locking; callers that share a registry across threads should serialize
    writes externally.
    """

    # ---------------------------------------------------------------- local

    def alloc_local_id(self) -> UUID:
        """Generate a new UUID and create its working directory.

        Returns the UUID. Use :meth:`local_path` to resolve it back to a
        :class:`pathlib.Path`. Repeated calls always return a fresh UUID;
        for "give me one if missing, else reuse", call :meth:`ensure_local`
        with an explicit id.
        """
        sid = uuid4()
        target = local_sandbox_dir(sid)
        target.mkdir(parents=True, exist_ok=True)
        return sid

    def ensure_local(self, sandbox_id: UUID | str) -> Path:
        """Create the working directory for ``sandbox_id`` if missing; return it.

        Idempotent. Useful when a caller already knows the id (e.g. from a
        persisted session header) and wants to rebind the same workdir.
        """
        target = local_sandbox_dir(sandbox_id)
        target.mkdir(parents=True, exist_ok=True)
        return target

    def local_path(self, sandbox_id: UUID | str) -> Path:
        """Resolve a local sandbox id to its on-disk working directory.

        Does not check existence — use :meth:`ensure_local` to create on
        demand. Returns the path even when the directory has been removed,
        so callers can decide whether to recreate.
        """
        return local_sandbox_dir(sandbox_id)

    def list_local(self) -> list[UUID]:
        """Enumerate UUID-named subdirectories under ``sandboxes/local/``."""
        root = local_root()
        if not root.is_dir():
            return []
        ids: list[UUID] = []
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            try:
                ids.append(UUID(entry.name))
            except ValueError:
                logger.debug("ignoring non-UUID dir in local sandboxes: %s", entry)
        return ids

    def delete_local(self, sandbox_id: UUID | str) -> bool:
        """Remove the on-disk working directory for a local sandbox.

        Returns ``True`` when the directory existed and was removed,
        ``False`` when it was already absent. Idempotent.
        """
        import shutil

        path = local_sandbox_dir(sandbox_id)
        if not path.exists():
            return False
        shutil.rmtree(path, ignore_errors=False)
        return True

    def prune_local(self, *, older_than: timedelta) -> list[UUID]:
        """Remove local sandbox dirs whose mtime is older than ``older_than``.

        Returns the list of removed ids in deletion order. Useful for a
        weekly cron / startup sweep — ``PersistentSandboxRegistry().prune_local(older_than=timedelta(days=30))``.
        """
        cutoff = datetime.now(timezone.utc) - older_than
        removed: list[UUID] = []
        for sid in self.list_local():
            path = local_sandbox_dir(sid)
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if mtime < cutoff and self.delete_local(sid):
                removed.append(sid)
        return removed

    # ---------------------------------------------------------------- remote

    def record_remote(
        self,
        backend: str,
        remote_id: str,
        spec: BackendSandboxSpec | None = None,
        *,
        sandbox_id: UUID | None = None,
    ) -> UUID:
        """Persist ``remote_id`` (e.g. an OpenSandbox ``native.id``) under a new UUID.

        ``backend`` is the backend name (typically ``"opensandbox"``).
        ``spec`` is the :class:`BackendSandboxSpec` used to create the
        remote sandbox; it round-trips through the same JSON projection as
        the session header. Returns the registry UUID (NOT ``remote_id``)
        so callers can keep using a stable local handle.
        """
        sid = sandbox_id or uuid4()
        now = datetime.now(timezone.utc)
        ensure_opensandbox_root()
        path = opensandbox_index_path(sid)
        record = {
            "schema_version": SCHEMA_VERSION,
            "id": str(sid),
            "backend": backend,
            "remote_id": remote_id,
            "spec": spec_to_jsonable(spec),
            "created_at": now.isoformat(),
            "last_used_at": now.isoformat(),
        }
        atomic_write_json(path, record)
        chmod_user_only(path)
        return sid

    def touch_remote(self, sandbox_id: UUID | str) -> None:
        """Update ``last_used_at`` on the remote sandbox index file.

        Silently no-ops when the record is missing — callers should rely on
        :meth:`load_remote` first if presence matters.
        """
        path = opensandbox_index_path(sandbox_id)
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("touch_remote: %s is unreadable", path, exc_info=True)
            return
        data["last_used_at"] = datetime.now(timezone.utc).isoformat()
        atomic_write_json(path, data)

    def load_remote(self, sandbox_id: UUID | str) -> RemoteSandboxRecord | None:
        """Read one remote-sandbox index file. Returns ``None`` when missing."""
        path = opensandbox_index_path(sandbox_id)
        if not path.is_file():
            return None
        return _decode_remote(path)

    def list_remote(self) -> list[RemoteSandboxRecord]:
        """Enumerate every remote sandbox record. Unreadable files are skipped."""
        root = opensandbox_root()
        if not root.is_dir():
            return []
        records: list[RemoteSandboxRecord] = []
        for entry in sorted(root.iterdir()):
            if not entry.is_file() or entry.suffix != ".json":
                continue
            decoded = _decode_remote(entry)
            if decoded is not None:
                records.append(decoded)
        records.sort(key=lambda r: r.created_at)
        return records

    def delete_remote(self, sandbox_id: UUID | str) -> bool:
        """Remove the index file for a recorded remote sandbox.

        Returns ``True`` when the file existed and was removed; ``False``
        when absent. Does **not** kill the remote container on the server —
        that's the caller's responsibility via the backend's ``close()``.
        """
        path = opensandbox_index_path(sandbox_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def prune_remote(self, *, older_than: timedelta) -> list[UUID]:
        """Remove index files whose ``last_used_at`` is older than ``older_than``.

        Returns the deleted ids in deletion order. The remote containers
        themselves are not touched.
        """
        cutoff = datetime.now(timezone.utc) - older_than
        removed: list[UUID] = []
        for record in self.list_remote():
            last_used = record.last_used_at
            if last_used.tzinfo is None:
                last_used = last_used.replace(tzinfo=timezone.utc)
            if last_used < cutoff and self.delete_remote(record.id):
                removed.append(record.id)
        return removed

    def reattach_remote(self, sandbox_id: UUID | str) -> BackendSandbox:
        """Reattach to a previously recorded remote sandbox by its registry id.

        Looks up the index file, then delegates to the named backend's
        ``attach`` method (currently only :class:`OpenSandboxBackend` provides
        one). Updates ``last_used_at`` on success.

        Raises :class:`KeyError` when the registry id is unknown, and
        ``AttributeError`` when the recorded backend has no ``attach`` —
        either path produces a clear error rather than silently creating a
        new container.
        """
        record = self.load_remote(sandbox_id)
        if record is None:
            raise KeyError(
                f"no remote sandbox recorded under id={sandbox_id!r}; "
                f"available: {[str(r.id) for r in self.list_remote()]}",
            )
        backend = backend_get(record.backend)
        attach = getattr(backend, "attach", None)
        if attach is None:
            raise AttributeError(
                f"backend {record.backend!r} does not support reattach "
                f"(no .attach(remote_id) method); cannot reuse remote_id "
                f"{record.remote_id!r}",
            )
        sandbox: BackendSandbox = attach(record.remote_id, spec=record.spec)
        self.touch_remote(record.id)
        return sandbox

    # ---------------------------------------------------------------- bootstrap

    def ensure_dirs(self) -> None:
        """Create both ``sandboxes/local/`` and ``sandboxes/opensandbox/`` roots."""
        ensure_local_root()
        ensure_opensandbox_root()


def _decode_remote(path: Path) -> RemoteSandboxRecord | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("unreadable remote-sandbox record: %s", path, exc_info=True)
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return RemoteSandboxRecord(
            schema_version=int(raw.get("schema_version", 0)),
            id=UUID(str(raw["id"])),
            backend=str(raw.get("backend", "")),
            remote_id=str(raw["remote_id"]),
            spec=spec_from_jsonable(raw.get("spec")),
            created_at=datetime.fromisoformat(str(raw["created_at"])),
            last_used_at=datetime.fromisoformat(str(raw["last_used_at"])),
            path=path,
        )
    except (KeyError, ValueError, TypeError):
        logger.warning("malformed remote-sandbox record: %s", path, exc_info=True)
        return None
