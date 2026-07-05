"""Unified retention / garbage collection across the persistence planes.

Each plane already had its own ``prune_*`` (sessions, local + remote sandboxes,
local memory stores), but there was no single entry point and — importantly —
nothing pruned the **memory commits archive** (``memory/local/<uuid>/session/
<sid>/commits/<ts>/``), which grew without bound on every ``commit_memory``.

``gc(older_than=..., dry_run=...)`` gives one opt-in sweep over all of them and
returns a :class:`GCReport` of what was (or would be) removed. ``dry_run=True``
(the default) reports without deleting. Every removed path is verified to live
under the resolved data root before deletion, so a bug can never delete outside
``.openrath/``.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

__all__ = ["GCReport", "gc"]

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GCReport:
    """What a :func:`gc` sweep removed (or would remove, in dry-run)."""

    sessions: list[UUID] = field(default_factory=list)
    local_sandboxes: list[UUID] = field(default_factory=list)
    remote_sandboxes: list[UUID] = field(default_factory=list)
    memory_stores: list[UUID] = field(default_factory=list)
    memory_commits: list[Path] = field(default_factory=list)
    dry_run: bool = True


def _data_root() -> Path:
    from rath.config.paths import resolve_config_dir

    return resolve_config_dir().resolve()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
        return True
    except ValueError:
        return False


def _collect_old_commits(root: Path, cutoff: datetime) -> list[Path]:
    """Find ``.../commits/<ts>/`` dirs older than ``cutoff`` under the memory plane."""
    from rath.memory.persistence.paths import local_memory_root

    mem_root = local_memory_root()
    if not mem_root.is_dir():
        return []
    found: list[Path] = []
    # memory/local/<store>/session/<sid>/commits/<ts>/
    for commits_dir in mem_root.glob("*/session/*/commits/*"):
        if not commits_dir.is_dir():
            continue
        if not _is_within(commits_dir, root):  # defense-in-depth
            continue
        try:
            mtime = datetime.fromtimestamp(commits_dir.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if mtime < cutoff:
            found.append(commits_dir)
    return sorted(found)


def gc(*, older_than: timedelta, dry_run: bool = True) -> GCReport:
    """Sweep prunable artifacts older than ``older_than`` across all planes.

    With ``dry_run=True`` (default) nothing is deleted — the report lists what
    *would* be removed. With ``dry_run=False`` the existing per-plane prune
    helpers run and the memory commits archive is trimmed. Deletion is confined
    to the resolved data root.
    """
    root = _data_root()
    cutoff = datetime.now(timezone.utc) - older_than
    report = GCReport(dry_run=dry_run)

    # --- memory commits archive (new; previously unbounded) ------------------
    commit_dirs = _collect_old_commits(root, cutoff)
    report.memory_commits = commit_dirs
    if not dry_run:
        for d in commit_dirs:
            if _is_within(d, root):
                shutil.rmtree(d, ignore_errors=True)

    # --- other planes --------------------------------------------------------
    if dry_run:
        report.sessions = _dry_sessions(cutoff)
        report.local_sandboxes = _dry_local_sandboxes(cutoff)
        report.remote_sandboxes = _dry_remote_sandboxes(cutoff)
        report.memory_stores = _dry_memory_stores(cutoff)
    else:
        from rath.backend.persistence.registry import PersistentSandboxRegistry
        from rath.memory.persistence.registry import PersistentMemoryRegistry
        from rath.session.persistence.loader import prune_sessions

        report.sessions = prune_sessions(older_than=older_than)
        sandbox_reg = PersistentSandboxRegistry()
        report.local_sandboxes = sandbox_reg.prune_local(older_than=older_than)
        report.remote_sandboxes = sandbox_reg.prune_remote(older_than=older_than)
        report.memory_stores = PersistentMemoryRegistry().prune_local(
            older_than=older_than
        )

    return report


# --- dry-run enumerators (mirror each prune's cutoff without deleting) -------


def _dry_sessions(cutoff: datetime) -> list[UUID]:
    from rath.session.persistence.loader import list_persisted_sessions

    out: list[UUID] = []
    for meta in list_persisted_sessions():
        created = meta.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created < cutoff:
            out.append(meta.id)
    return out


def _dry_local_sandboxes(cutoff: datetime) -> list[UUID]:
    from rath.backend.persistence.paths import local_sandbox_dir
    from rath.backend.persistence.registry import PersistentSandboxRegistry

    out: list[UUID] = []
    for sid in PersistentSandboxRegistry().list_local():
        try:
            mtime = datetime.fromtimestamp(
                local_sandbox_dir(sid).stat().st_mtime, tz=timezone.utc
            )
        except OSError:
            continue
        if mtime < cutoff:
            out.append(sid)
    return out


def _dry_remote_sandboxes(cutoff: datetime) -> list[UUID]:
    from rath.backend.persistence.registry import PersistentSandboxRegistry

    reg = PersistentSandboxRegistry()
    out: list[UUID] = []
    for rec in reg.list_remote():
        last = rec.last_used_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last < cutoff:
            out.append(rec.id)
    return out


def _dry_memory_stores(cutoff: datetime) -> list[UUID]:
    from rath.memory.persistence.paths import local_store_dir
    from rath.memory.persistence.registry import PersistentMemoryRegistry

    out: list[UUID] = []
    for sid in PersistentMemoryRegistry().list_local():
        try:
            mtime = datetime.fromtimestamp(
                local_store_dir(sid).stat().st_mtime, tz=timezone.utc
            )
        except OSError:
            continue
        if mtime < cutoff:
            out.append(sid)
    return out
