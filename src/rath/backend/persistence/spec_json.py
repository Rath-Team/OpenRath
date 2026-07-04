"""JSONable round-trip for :class:`BackendSandboxSpec`.

Shared by the backend registry (``rath.backend.persistence.registry``) and the
session writer (``rath.session.persistence._serialize``); :data:`SCHEMA_VERSION`
versions both on-disk formats so they bump together.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from rath.backend.abc import BackendSandboxSpec

__all__ = ["SCHEMA_VERSION", "spec_to_jsonable", "spec_from_jsonable"]

SCHEMA_VERSION = 1


def spec_to_jsonable(spec: BackendSandboxSpec | None) -> dict[str, Any] | None:
    """Project :class:`BackendSandboxSpec` into a plain-dict shape.

    ``timedelta`` becomes total seconds (``float``); ``Sequence`` /
    ``Mapping`` become ``list`` / ``dict``. Returns ``None`` when ``spec`` is
    ``None``.
    """
    if spec is None:
        return None
    return {
        "image": spec.image,
        "entrypoint": list(spec.entrypoint) if spec.entrypoint is not None else None,
        "env": dict(spec.env) if spec.env is not None else None,
        "timeout_seconds": (
            spec.timeout.total_seconds() if spec.timeout is not None else None
        ),
        "working_dir": spec.working_dir,
    }


def spec_from_jsonable(raw: dict[str, Any] | None) -> BackendSandboxSpec | None:
    """Inverse of :func:`spec_to_jsonable`."""
    if raw is None:
        return None
    timeout_s = raw.get("timeout_seconds")
    entrypoint = raw.get("entrypoint")
    env = raw.get("env")
    return BackendSandboxSpec(
        image=raw.get("image"),
        entrypoint=tuple(entrypoint) if entrypoint is not None else None,
        env=dict(env) if env is not None else None,
        timeout=timedelta(seconds=float(timeout_s)) if timeout_s is not None else None,
        working_dir=raw.get("working_dir"),
    )
