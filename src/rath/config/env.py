"""Central registry of every environment variable OpenRath reads.

Historically each client (openai/anthropic/litellm, sync and async) read
``os.environ.get(...)`` with bare string literals, duplicated line-for-line
across the sync and async paths. This module declares each variable **once**
with its kind, consumers, and default, and offers a single typed read plus a
precedence-preserving :func:`resolve_env`.

It deliberately does **not** rename or re-prefix any variable — the existing
vendor names (``OPENAI_API_KEY`` etc.) are kept exactly. The registry is a
lookup + documentation + single-read layer, not a new naming scheme.

Precedence is unchanged: **explicit field > environment > config**. Callers
express that via ``resolve_env(name, *explicit_candidates)``, which returns the
first non-empty value among the explicit candidates and then the env var
(mirroring :func:`rath.llm.credentials.resolve_credential`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "EnvKind",
    "EnvSpec",
    "get_env_spec",
    "env_value",
    "env_flag",
    "resolve_env",
    "env_reference_rows",
    "all_env_specs",
]


class EnvKind(Enum):
    """What a variable carries, for docs and secret-hygiene decisions."""

    SECRET = "secret"  # api keys — never log the value
    ROUTING = "routing"  # base urls, model names, endpoints, home dir
    FLAG = "flag"  # boolean toggles


_TRUTHY = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True, slots=True)
class EnvSpec:
    """Declaration of a single environment variable."""

    name: str
    kind: EnvKind
    consumers: str  # human-readable "who reads this and for what"
    default: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)


# --- The registry -----------------------------------------------------------
# Declared once here; see rath.llm.* and rath.backend.opensandbox for consumers.

_SPECS: dict[str, EnvSpec] = {}


def _register(spec: EnvSpec) -> None:
    _SPECS[spec.name] = spec


def get_env_spec(name: str) -> EnvSpec:
    """Return the declared :class:`EnvSpec`, or raise :class:`KeyError`."""
    try:
        return _SPECS[name]
    except KeyError as e:
        raise KeyError(
            f"{name!r} is not a declared OpenRath environment variable; "
            f"declared: {sorted(_SPECS)}"
        ) from e


def env_value(name: str, *, environ: dict[str, str] | None = None) -> str | None:
    """Return the stripped value of ``name``, or its default, or ``None``.

    Raises :class:`KeyError` if ``name`` is not declared (typo guard).
    Whitespace-only values are treated as unset.
    """
    spec = get_env_spec(name)
    src = os.environ if environ is None else environ
    raw = src.get(name)
    if raw is not None:
        s = raw.strip()
        if s:
            return s
    return spec.default


def env_flag(name: str, *, environ: dict[str, str] | None = None) -> bool:
    """Interpret ``name`` as a boolean flag (``1/true/yes/on`` → True)."""
    val = env_value(name, environ=environ)
    if val is None:
        return False
    return val.lower() in _TRUTHY


def resolve_env(name: str, *explicit: str | None) -> str:
    """First non-empty among ``explicit`` candidates, then the env var.

    Mirrors :func:`rath.llm.credentials.resolve_credential`, preserving the
    documented ``explicit > env`` precedence. Returns ``""`` when nothing
    qualifies; callers decide whether that is an error. (Config-file fallback
    stays in the caller — the registry only owns the env tier.)
    """
    for c in explicit:
        if c is not None and c.strip():
            return c.strip()
    val = env_value(name)
    return val if val is not None else ""


def all_env_specs() -> list[EnvSpec]:
    """All declared specs, sorted by name."""
    return [_SPECS[n] for n in sorted(_SPECS)]


def env_reference_rows() -> list[dict[str, str]]:
    """Sorted, JSON-friendly rows for a generated reference table (P2.4)."""
    rows: list[dict[str, str]] = []
    for spec in all_env_specs():
        rows.append(
            {
                "name": spec.name,
                "kind": spec.kind.value,
                "consumers": spec.consumers,
                "default": "" if spec.default is None else spec.default,
            }
        )
    return rows


# --- Declarations (the single source of truth) ------------------------------

# Home / paths
_register(
    EnvSpec(
        "OPENRATH_HOME",
        EnvKind.ROUTING,
        "rath.config.paths: overrides the config/data root dir",
    )
)

# OpenAI-compatible
_register(
    EnvSpec(
        "OPENAI_API_KEY", EnvKind.SECRET, "OpenAI-compatible chat/embed/vlm api key"
    )
)
_register(EnvSpec("OPENAI_BASE_URL", EnvKind.ROUTING, "OpenAI-compatible base url"))
_register(
    EnvSpec(
        "OPENAI_DEFAULT_MODEL",
        EnvKind.ROUTING,
        "default model for OpenAI-compatible clients",
    )
)
_register(
    EnvSpec(
        "OPENAI_API_VERSION",
        EnvKind.ROUTING,
        "legacy Azure api_version (client applies a 2024-10-21 fallback)",
    )
)

# Azure OpenAI
_register(EnvSpec("AZURE_OPENAI_ENDPOINT", EnvKind.ROUTING, "Azure OpenAI endpoint"))
_register(EnvSpec("AZURE_OPENAI_API_KEY", EnvKind.SECRET, "Azure OpenAI api key"))
_register(EnvSpec("AZURE_API_KEY", EnvKind.SECRET, "Azure api key (fallback)"))
_register(
    EnvSpec("AZURE_OPENAI_API_VERSION", EnvKind.ROUTING, "Azure api_version (fallback)")
)

# Anthropic
_register(EnvSpec("ANTHROPIC_API_KEY", EnvKind.SECRET, "Anthropic api key"))
_register(EnvSpec("ANTHROPIC_BASE_URL", EnvKind.ROUTING, "Anthropic base url"))
_register(
    EnvSpec(
        "ANTHROPIC_DEFAULT_MODEL",
        EnvKind.ROUTING,
        "default model for the Anthropic client",
    )
)

# LiteLLM
_register(EnvSpec("LITELLM_API_KEY", EnvKind.SECRET, "LiteLLM api key"))
_register(EnvSpec("LITELLM_API_BASE", EnvKind.ROUTING, "LiteLLM api base url"))
_register(
    EnvSpec("LITELLM_MODEL", EnvKind.ROUTING, "default model for the LiteLLM client")
)

# OpenSandbox backend
_register(
    EnvSpec(
        "OPEN_SANDBOX_DOMAIN",
        EnvKind.ROUTING,
        "opensandbox service domain",
        aliases=("OPENSANDBOX_DOMAIN",),
    )
)
_register(
    EnvSpec(
        "OPENSANDBOX_DOMAIN",
        EnvKind.ROUTING,
        "opensandbox service domain (legacy alias)",
    )
)
_register(
    EnvSpec(
        "OPEN_SANDBOX_API_KEY",
        EnvKind.SECRET,
        "opensandbox api key (read by the SDK, not rath directly)",
    )
)
_register(
    EnvSpec(
        "RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND",
        EnvKind.FLAG,
        "opensandbox: fail instead of falling back when workspace bind is rejected",
    )
)
