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
    "MCPServerConfig",
    "MCPConfig",
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

    provider_kind: Literal["openai", "anthropic"] = "openai"
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


class RathConfig(BaseModel):
    """Top-level on-disk schema.

    Sections currently in use: ``llm`` and ``mcp``. Future sections (e.g.
    ``backend`` for OpenSandbox routing) can be added without touching
    callers because ``extra="allow"`` preserves them on round-trip.
    """

    version: int = SCHEMA_VERSION
    llm: LLMConfig = Field(default_factory=LLMConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)

    model_config = ConfigDict(extra="allow")
