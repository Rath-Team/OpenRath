"""Root layout manifest for the ``.openrath/`` data root.

Historically each plane carried its own ``SCHEMA_VERSION`` (config, backend
spec-json, memory meta) with no coordination and no record of the overall
on-disk *layout*. ``manifest.json`` at the data root records the layout version
plus a snapshot of every plane's schema version, so:

- an upgrade can detect an older/newer layout deterministically;
- a newer OpenRath's data root is refused with a clear error rather than being
  silently misread by an older install.

The manifest is intentionally tiny and additive. Writing it is best-effort at
the persistence boundary; :func:`check_manifest` is a no-op when it is absent
(fresh or legacy root), so it never breaks existing installs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rath.persistence.atomic import atomic_write_json

__all__ = [
    "LAYOUT_VERSION",
    "MANIFEST_FILENAME",
    "ManifestVersionError",
    "plane_schema_versions",
    "read_manifest",
    "ensure_manifest",
    "check_manifest",
]

#: Bump when the overall on-disk directory layout changes (not when a single
#: plane's schema changes — those are tracked per-plane below).
LAYOUT_VERSION = 1

MANIFEST_FILENAME = "manifest.json"


class ManifestVersionError(RuntimeError):
    """Raised when the on-disk layout version is newer than this install."""


def plane_schema_versions() -> dict[str, int]:
    """Snapshot each plane's current schema version.

    Imported lazily so this module has no import-time dependency on the
    config/backend/memory packages (avoids import cycles).
    """
    from rath.backend.persistence.spec_json import SCHEMA_VERSION as BACKEND_V
    from rath.config.schema import SCHEMA_VERSION as CONFIG_V
    from rath.memory.adapters.local import META_SCHEMA_VERSION as MEMORY_V

    return {"config": CONFIG_V, "backend": BACKEND_V, "memory": MEMORY_V}


def _manifest_path(root: Path) -> Path:
    return root / MANIFEST_FILENAME


def read_manifest(root: Path) -> dict[str, Any] | None:
    """Return the parsed manifest, or ``None`` when absent/unreadable."""
    path = _manifest_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def ensure_manifest(root: Path) -> dict[str, Any]:
    """Create the manifest if missing; return the effective manifest.

    Idempotent: an existing current-layout manifest is refreshed with the
    latest per-plane schema versions but keeps its layout version.
    """
    existing = read_manifest(root)
    manifest: dict[str, Any] = {
        "layout_version": LAYOUT_VERSION,
        "planes": plane_schema_versions(),
    }
    if existing == manifest:
        return existing
    atomic_write_json(_manifest_path(root), manifest)
    return manifest


def check_manifest(root: Path) -> None:
    """Raise :class:`ManifestVersionError` if the layout is newer than ours.

    No-op when the manifest is absent (fresh or legacy root) — this must never
    break an install that predates the manifest.
    """
    data = read_manifest(root)
    if data is None:
        return
    on_disk = data.get("layout_version")
    if isinstance(on_disk, int) and on_disk > LAYOUT_VERSION:
        raise ManifestVersionError(
            f"{_manifest_path(root)} has layout_version={on_disk}, newer than this "
            f"OpenRath (supports {LAYOUT_VERSION}); upgrade OpenRath to read this "
            f"data root safely."
        )
