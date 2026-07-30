"""Filesystem layout for persisted sandboxes.

Shares the resolved ``.openrath/`` root with :mod:`rath.config` and
:mod:`rath.session.persistence`. Local sandboxes get a stable working
directory; OpenSandbox sandboxes get an index JSON recording the remote id
and last-used timestamp.

These functions are pure: they describe paths and (optionally) ``mkdir``
the parent. No content is read or written here.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from rath.config.paths import resolve_config_dir
from rath.utils.ids import coerce_uuid_str

__all__ = [
    "SANDBOXES_DIR_NAME",
    "LOCAL_SUBDIR",
    "OPENSANDBOX_SUBDIR",
    "OPENSANDBOX_INDEX_SUFFIX",
    "sandboxes_dir",
    "local_root",
    "local_sandbox_dir",
    "opensandbox_root",
    "opensandbox_index_path",
    "ensure_local_root",
    "ensure_opensandbox_root",
]

SANDBOXES_DIR_NAME = "sandboxes"
LOCAL_SUBDIR = "local"
OPENSANDBOX_SUBDIR = "opensandbox"
OPENSANDBOX_INDEX_SUFFIX = ".json"


def sandboxes_dir() -> Path:
    """``<resolved-config-dir>/sandboxes`` (not created)."""
    return resolve_config_dir() / SANDBOXES_DIR_NAME


def local_root() -> Path:
    """``<resolved-config-dir>/sandboxes/local`` (not created)."""
    return sandboxes_dir() / LOCAL_SUBDIR


def local_sandbox_dir(sandbox_id: UUID | str) -> Path:
    """``<local_root>/<sandbox_id>`` — the stable working_dir for a Local sandbox."""
    return local_root() / coerce_uuid_str(sandbox_id, field="sandbox_id")


def opensandbox_root() -> Path:
    """``<resolved-config-dir>/sandboxes/opensandbox`` (not created)."""
    return sandboxes_dir() / OPENSANDBOX_SUBDIR


def opensandbox_index_path(sandbox_id: UUID | str) -> Path:
    """``<opensandbox_root>/<sandbox_id>.json`` — registry entry for a remote sandbox."""
    sid = coerce_uuid_str(sandbox_id, field="sandbox_id")
    return opensandbox_root() / f"{sid}{OPENSANDBOX_INDEX_SUFFIX}"


def ensure_local_root() -> Path:
    """Create ``sandboxes/local/`` (and parents) if missing; return the path."""
    target = local_root()
    target.mkdir(parents=True, exist_ok=True)
    return target


def ensure_opensandbox_root() -> Path:
    """Create ``sandboxes/opensandbox/`` (and parents) if missing; return the path."""
    target = opensandbox_root()
    target.mkdir(parents=True, exist_ok=True)
    return target
