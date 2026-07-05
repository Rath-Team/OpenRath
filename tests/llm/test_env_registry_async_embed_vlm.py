"""P2.3 — async clients + embedding/vlm resolve through the EnvSpec registry.

- async openai/anthropic resolvers preserve precedence (refactor guard);
- embedding.py / vlm.py gain the config-file fallback that chat clients have
  (previously they only consulted Provider + env), routed via env_value.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from rath.config.paths import resolve_config_path
from rath.config.store import ConfigStore
from rath.llm.embedding import EmbeddingProvider
from rath.llm.provider import Provider
from rath.llm.vlm import VLMProvider


@pytest.fixture(autouse=True)
def _isolate_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("OPENRATH_HOME", str(tmp_path / "home"))
    ConfigStore._cache.clear()
    yield
    ConfigStore._cache.clear()


def test_async_openai_resolvers_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    from rath._async.aopenai import _resolve_api_key, _resolve_base_url

    monkeypatch.setenv("OPENAI_BASE_URL", "https://aenv/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-aenv")
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    assert _resolve_base_url(Provider(base_url="https://ax/v1")) == "https://ax/v1"
    assert _resolve_base_url(Provider()) == "https://aenv/v1"
    assert _resolve_api_key(Provider(api_key="sk-ax"), "") == "sk-ax"
    assert _resolve_api_key(Provider(), "https://api.openai.com/v1") == "sk-aenv"


def test_async_anthropic_resolver_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    from rath._async.aanthropic import _resolve_async_anthropic_key

    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak-aenv")
    assert _resolve_async_anthropic_key(Provider(api_key="ak-ax")) == "ak-ax"
    assert _resolve_async_anthropic_key(Provider()) == "ak-aenv"


def test_embedding_config_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """EmbeddingProvider with no key/env resolves from llm config (new in P2.3)."""
    from rath.config.schema import LLMProviderConfig
    from rath.llm.embedding import _resolve_api_key, _resolve_base_url

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    store = ConfigStore(path=resolve_config_path())
    store.config.llm.providers["main"] = LLMProviderConfig(
        provider_kind="openai", api_key="sk-cfg-embed", base_url="https://cfg/v1"
    )
    store.config.llm.default_provider = "main"
    store.save()
    ConfigStore._cache.clear()

    assert (
        _resolve_api_key(EmbeddingProvider(model="text-embedding-3-small"))
        == "sk-cfg-embed"
    )
    assert (
        _resolve_base_url(EmbeddingProvider(model="text-embedding-3-small"))
        == "https://cfg/v1"
    )
    # Explicit still wins.
    assert _resolve_api_key(EmbeddingProvider(model="m", api_key="sk-x")) == "sk-x"


def test_vlm_config_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from rath.config.schema import LLMProviderConfig
    from rath.llm.vlm import _resolve_api_key, _resolve_base_url

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    store = ConfigStore(path=resolve_config_path())
    store.config.llm.providers["main"] = LLMProviderConfig(
        provider_kind="openai", api_key="sk-cfg-vlm", base_url="https://cfgv/v1"
    )
    store.config.llm.default_provider = "main"
    store.save()
    ConfigStore._cache.clear()

    assert _resolve_api_key(VLMProvider(model="gpt-4o")) == "sk-cfg-vlm"
    assert _resolve_base_url(VLMProvider(model="gpt-4o")) == "https://cfgv/v1"


def test_no_bare_os_environ_in_refactored_modules() -> None:
    """Guard: refactored modules read env only through the registry."""
    import rath._async.aanthropic as aanthropic
    import rath._async.aopenai as aopenai
    import rath.llm.embedding as embedding
    import rath.llm.vlm as vlm

    for mod in (aopenai, aanthropic, embedding, vlm):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "os.environ.get(" not in src, f"{mod.__name__} still uses os.environ.get"
