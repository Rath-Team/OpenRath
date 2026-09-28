"""Pydantic v2 schema for ``~/.openrath/config.json``.

Every model uses ``extra="allow"`` so unknown fields written by a newer
OpenRath or a third-party tool round-trip through load → save without loss.
Schema is versioned via :attr:`RathConfig.version`; no migration code yet,
but the field is reserved so v2 can detect older files.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "LLMProviderConfig",
    "LLMConfig",
    "MemoryProviderConfig",
    "MemoryConfig",
    "MCPServerConfig",
    "MCPConfig",
    "BackendProviderConfig",
    "BackendConfig",
    "RathConfig",
    "SCHEMA_VERSION",
]

SCHEMA_VERSION = 1


class LLMProviderConfig(BaseModel):
    """One named entry under ``llm.providers``.

    Mirrors the most common :class:`~rath.llm.Provider` fields. Less-common
    knobs (``frequency_penalty``, ``logit_bias``, …) stay on explicit
    ``Provider(...)`` kwargs — adding fields here later is non-breaking thanks
    to ``extra="allow"``.
    """

    provider_kind: Literal["openai", "anthropic", "litellm", "atlascloud"] = "openai"
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None

    model_config = ConfigDict(extra="allow")


class LLMConfig(BaseModel):
    """The ``llm`` section: named providers + which one is the default.

    ``default_provider`` is the chat fallback. ``embedding_provider`` and
    ``vlm_provider`` are independent overrides used by
    :class:`rath.llm.embedding.EmbeddingProvider` and
    :class:`rath.llm.vlm.VLMProvider`; when unset, those clients fall back
    to ``default_provider``'s ``api_key``/``base_url`` with a sensible
    default model.
    """

    default_provider: str | None = None
    embedding_provider: str | None = None
    vlm_provider: str | None = None
    providers: dict[str, LLMProviderConfig] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class MCPServerConfig(BaseModel):
    """One named entry under ``mcp.servers``.

    ``command`` is the full argv list passed to the stdio MCP server (the
    OpenRath adapter never shells out, so no string-form). ``env`` is
    merged into the subprocess environment by the adapter.
    """

    command: list[str]
    env: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class MCPConfig(BaseModel):
    """The ``mcp`` section: named server defs + which are enabled by default."""

    default_enabled: list[str] = Field(default_factory=list)
    servers: dict[str, MCPServerConfig] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class MemoryProviderConfig(BaseModel):
    """One named entry under ``memory.providers`` (local backend only).

    ``embedding_provider`` and ``chat_provider`` name entries under
    ``llm.providers`` used by :class:`~rath.memory.adapters.local.LocalMemoryBackend`
    for vector search and commit-time memo extraction respectively.
    OpenViking connection settings stay on ``MemoryStoreSpec.options`` or
    environment variables — they are not modeled here.
    """

    backend_kind: Literal["local"] = "local"
    path: str | None = None
    embedding_provider: str | None = None
    chat_provider: str | None = None

    model_config = ConfigDict(extra="allow")


class MemoryConfig(BaseModel):
    """The ``memory`` section: named local store presets."""

    default_provider: str | None = None
    providers: dict[str, MemoryProviderConfig] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class BackendProviderConfig(BaseModel):
    """One named entry under ``backend.providers``.

    Gives sandbox backends a config home parallel to ``llm``/``memory`` instead
    of relying on environment variables and ``~/.sandbox.toml`` alone. ``domain``
    and ``api_key`` route the ``opensandbox`` backend; ``api_key`` is a secret
    and is externalized to ``credentials.json`` on save (see
    :mod:`rath.config.credentials`). Backend-specific knobs (image, timeout, …)
    stay on ``options`` and round-trip via ``extra="allow"``.
    """

    backend_kind: Literal["local", "opensandbox"] = "opensandbox"
    domain: str | None = None
    api_key: str | None = None
    options: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class BackendConfig(BaseModel):
    """The ``backend`` section: named sandbox-backend presets + the default."""

    default_provider: str | None = None
    providers: dict[str, BackendProviderConfig] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class RathConfig(BaseModel):
    """Top-level on-disk schema.

    Sections currently in use: ``llm``, ``mcp``, ``memory``, and ``backend``.
    Unknown/future sections are preserved on round-trip because
    ``extra="allow"``.
    """

    version: int = SCHEMA_VERSION
    llm: LLMConfig = Field(default_factory=LLMConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    backend: BackendConfig = Field(default_factory=BackendConfig)

    model_config = ConfigDict(extra="allow")
