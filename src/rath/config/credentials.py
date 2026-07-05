"""Split secrets out of the routing config into a separate ``credentials.json``.

The in-memory :class:`~rath.config.schema.RathConfig` keeps ``api_key`` inline
so callers are unaffected. On disk, secrets live in a sibling
``credentials.json`` (0600) while ``config.json`` holds only routing/presets.
This keeps a project-local ``config.json`` safe to eyeball / share without
leaking keys, and lets the two files carry different permissions.

The functions here are pure dict transforms so they can be unit-tested without
touching the filesystem; :class:`~rath.config.store.ConfigStore` calls them at
the load/save boundary.

Secret layout in ``credentials.json``::

    {"version": 1, "llm": {"providers": {"<name>": "<api_key>"}},
                    "backend": {"providers": {"<name>": "<api_key>"}}}

Only sections that hold a ``providers`` mapping with an ``api_key`` field are
considered. Adding a new such section (e.g. ``backend`` in P1.2) needs only a
one-line addition to :data:`SECRET_SECTIONS`.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "CREDENTIALS_FILENAME",
    "SECRET_SECTIONS",
    "split_secrets",
    "secrets_from_config",
]

CREDENTIALS_FILENAME = "credentials.json"

# Config sections whose ``providers[*].api_key`` is a secret to externalize.
SECRET_SECTIONS: tuple[str, ...] = ("llm", "backend")


def split_secrets(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(config_without_secrets, credentials)`` from a full dump.

    ``payload`` is mutated-safe: a shallow-enough copy is made so the caller's
    dict is not modified. Each provider's non-empty ``api_key`` is moved into
    the credentials mapping and removed from the config mapping.
    """
    import copy

    config = copy.deepcopy(payload)
    creds: dict[str, Any] = {}

    for section in SECRET_SECTIONS:
        sect = config.get(section)
        if not isinstance(sect, dict):
            continue
        providers = sect.get("providers")
        if not isinstance(providers, dict):
            continue
        for name, entry in providers.items():
            if not isinstance(entry, dict):
                continue
            key = entry.get("api_key")
            if key:
                entry.pop("api_key", None)
                creds.setdefault(section, {}).setdefault("providers", {})[name] = key

    return config, creds


def secrets_from_config(credentials: dict[str, Any]) -> dict[tuple[str, str], str]:
    """Flatten a loaded ``credentials.json`` into ``{(section, name): api_key}``."""
    out: dict[tuple[str, str], str] = {}
    for section in SECRET_SECTIONS:
        sect = credentials.get(section)
        if not isinstance(sect, dict):
            continue
        providers = sect.get("providers")
        if not isinstance(providers, dict):
            continue
        for name, key in providers.items():
            if isinstance(key, str) and key:
                out[(section, name)] = key
    return out
