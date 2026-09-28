"""Pydantic schema tests — real validation, no mocks."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rath.config.schema import (
    SCHEMA_VERSION,
    LLMConfig,
    LLMProviderConfig,
    MCPConfig,
    MCPServerConfig,
    MemoryConfig,
    MemoryProviderConfig,
    RathConfig,
)


def test_defaults_round_trip_to_known_shape() -> None:
    cfg = RathConfig()
    payload = cfg.model_dump(mode="json")
    assert payload == {
        "version": SCHEMA_VERSION,
        "llm": {
            "default_provider": None,
            "embedding_provider": None,
            "vlm_provider": None,
            "providers": {},
        },
        "mcp": {"default_enabled": [], "servers": {}},
        "memory": {"default_provider": None, "providers": {}},
        "backend": {"default_provider": None, "providers": {}},
    }
    c = LLMConfig(
        default_provider="chat",
        embedding_provider="embed",
        vlm_provider="vis",
        providers={
            "chat": LLMProviderConfig(provider_kind="openai", model="gpt-x"),
            "embed": LLMProviderConfig(provider_kind="openai", model="emb-x"),
            "vis": LLMProviderConfig(provider_kind="openai", model="glm-4.6v"),
        },
    )
    assert c.embedding_provider == "embed"
    assert c.vlm_provider == "vis"
    # Round-trip through json preserves the new fields.
    dumped = c.model_dump(mode="json")
    rebuilt = LLMConfig.model_validate(dumped)
    assert rebuilt.embedding_provider == "embed"
    assert rebuilt.vlm_provider == "vis"


def test_legacy_config_without_new_fields_loads_with_none_defaults() -> None:
    """A pre-existing config.json missing the new keys must keep loading."""
    legacy = {
        "version": 1,
        "llm": {
            "default_provider": "x",
            "providers": {
                "x": {"provider_kind": "openai", "model": "y"},
            },
        },
        "mcp": {"default_enabled": [], "servers": {}},
    }
    cfg = RathConfig.model_validate(legacy)
    assert cfg.llm.embedding_provider is None
    assert cfg.llm.vlm_provider is None
    # Default chat path still works.
    assert cfg.llm.default_provider == "x"


def test_memory_config_accepts_local_provider() -> None:
    c = MemoryConfig(
        default_provider="local-main",
        providers={
            "local-main": MemoryProviderConfig(
                path="/data/memory",
                embedding_provider="embed",
                chat_provider="chat",
            ),
        },
    )
    assert c.default_provider == "local-main"
    entry = c.providers["local-main"]
    assert entry.backend_kind == "local"
    assert entry.embedding_provider == "embed"
    assert entry.chat_provider == "chat"


def test_legacy_config_without_memory_section_loads_defaults() -> None:
    legacy = {
        "version": 1,
        "llm": {"default_provider": None, "providers": {}},
        "mcp": {"default_enabled": [], "servers": {}},
    }
    cfg = RathConfig.model_validate(legacy)
    assert cfg.memory.default_provider is None
    assert cfg.memory.providers == {}


def test_llm_provider_rejects_unknown_provider_kind() -> None:
    with pytest.raises(ValidationError):
        LLMProviderConfig(provider_kind="bogus")  # type: ignore[arg-type]


def test_llm_provider_accepts_builtin_provider_kinds() -> None:
    a = LLMProviderConfig(provider_kind="openai", model="gpt-5")
    b = LLMProviderConfig(provider_kind="anthropic", model="claude-opus-4-7")
    c = LLMProviderConfig(provider_kind="atlascloud", model="qwen/qwen3.5-flash")
    assert a.provider_kind == "openai"
    assert b.provider_kind == "anthropic"
    assert c.provider_kind == "atlascloud"


def test_extra_allow_round_trips_unknown_keys() -> None:
    src = {
        "version": 1,
        "llm": {
            "default_provider": "x",
            "providers": {
                "x": {
                    "provider_kind": "openai",
                    "api_key": "sk-x",
                    "future_field": {"nested": True},
                }
            },
            "experiment.flag": "on",
        },
        "mcp": {"default_enabled": [], "servers": {}},
        "future_section": {"some": "future-section"},
    }
    cfg = RathConfig.model_validate(src)
    dumped = cfg.model_dump(mode="json")
    # Unknown top-level "future_section", unknown llm-level "experiment.flag",
    # and unknown provider-level "future_field" all survive the round-trip.
    assert dumped["future_section"] == {"some": "future-section"}
    assert dumped["llm"]["experiment.flag"] == "on"
    assert dumped["llm"]["providers"]["x"]["future_field"] == {"nested": True}


def test_mcp_server_empty_command_is_valid_but_degenerate() -> None:
    s = MCPServerConfig(command=[])
    assert s.command == []
    assert s.env == {}


def test_mcp_config_default_enabled_preserves_order() -> None:
    c = MCPConfig(default_enabled=["b", "a", "c"], servers={})
    assert c.default_enabled == ["b", "a", "c"]


def test_llm_config_providers_is_a_dict_not_list() -> None:
    c = LLMConfig(
        default_provider="m",
        providers={
            "m": LLMProviderConfig(provider_kind="openai"),
        },
    )
    assert isinstance(c.providers, dict)
    assert "m" in c.providers
