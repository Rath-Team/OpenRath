"""Real-fs tests for :meth:`rath.llm.Provider.from_config`.

No mocks. Each test writes a real config.json and asks Provider to read it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rath.config.schema import LLMProviderConfig
from rath.config.store import ConfigStore
from rath.llm import Provider


def _build_store_with(tmp_path: Path, **providers: LLMProviderConfig) -> ConfigStore:
    cfg_path = tmp_path / "config.json"
    store = ConfigStore(path=cfg_path)
    for name, entry in providers.items():
        store.config.llm.providers[name] = entry
    store.save()
    return ConfigStore(path=cfg_path)  # re-load to mirror real usage


def test_named_provider_round_trips_into_provider(tmp_path: Path) -> None:
    store = _build_store_with(
        tmp_path,
        main=LLMProviderConfig(
            provider_kind="openai",
            model="gpt-5",
            api_key="sk-from-config",
            base_url="https://api.example.com/v1",
            temperature=0.3,
            max_tokens=512,
        ),
    )
    p = Provider.from_config("main", store=store)
    assert p.provider_kind == "openai"
    assert p.model == "gpt-5"
    assert p.api_key == "sk-from-config"
    assert p.base_url == "https://api.example.com/v1"
    assert p.temperature == 0.3
    assert p.max_tokens == 512


def test_default_provider_used_when_name_omitted(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    store = ConfigStore(path=cfg_path)
    store.config.llm.default_provider = "claude"
    store.config.llm.providers["claude"] = LLMProviderConfig(
        provider_kind="anthropic",
        model="claude-opus-4-7",
        api_key="sk-ant-default",
    )
    store.save()
    reloaded = ConfigStore(path=cfg_path)
    p = Provider.from_config(None, store=reloaded)
    assert p.provider_kind == "anthropic"
    assert p.api_key == "sk-ant-default"


def test_atlascloud_provider_round_trips_into_provider(tmp_path: Path) -> None:
    store = _build_store_with(
        tmp_path,
        atlas=LLMProviderConfig(
            provider_kind="atlascloud",
            model="deepseek-ai/deepseek-v4-pro",
            api_key="ak-from-config",
        ),
    )
    p = Provider.from_config("atlas", store=store)
    assert p.provider_kind == "atlascloud"
    assert p.model == "deepseek-ai/deepseek-v4-pro"
    assert p.api_key == "ak-from-config"


def test_explicit_kwargs_override_config_fields(tmp_path: Path) -> None:
    store = _build_store_with(
        tmp_path,
        main=LLMProviderConfig(
            provider_kind="openai",
            model="gpt-5",
            api_key="sk-config",
        ),
    )
    p = Provider.from_config(
        "main", store=store, api_key="sk-override", temperature=0.9
    )
    assert p.api_key == "sk-override"
    assert p.temperature == 0.9
    # Non-overridden fields still come from config.
    assert p.model == "gpt-5"


def test_unknown_name_raises_with_available_listed(tmp_path: Path) -> None:
    store = _build_store_with(
        tmp_path,
        alpha=LLMProviderConfig(),
        beta=LLMProviderConfig(),
    )
    with pytest.raises(KeyError) as exc_info:
        Provider.from_config("gamma", store=store)
    msg = str(exc_info.value)
    assert "gamma" in msg
    assert "alpha" in msg
    assert "beta" in msg


def test_missing_default_provider_raises_clearly(tmp_path: Path) -> None:
    store = ConfigStore(path=tmp_path / "config.json")
    # No providers, no default. from_config(None) should fail loudly.
    with pytest.raises(KeyError, match="no LLM provider name"):
        Provider.from_config(None, store=store)


def test_real_filesystem_end_to_end(tmp_path: Path) -> None:
    """Whole flow: write config.json, reload via ConfigStore.load(), build Provider.

    Avoids the explicit ``store=`` kwarg, so it exercises the default
    ``ConfigStore.load()`` path through the OPENRATH_HOME fixture.
    """
    cfg_path = tmp_path / "openrath_home" / "config.json"
    cfg_path.parent.mkdir(parents=True)
    s = ConfigStore(path=cfg_path)
    s.config.llm.default_provider = "real"
    s.config.llm.providers["real"] = LLMProviderConfig(
        provider_kind="openai", model="gpt-5", api_key="sk-real-fs"
    )
    s.save()
    p = Provider.from_config("real")  # uses OPENRATH_HOME via fixture
    assert p.api_key == "sk-real-fs"
