"""Real-fs tests for :meth:`rath.memory.abc.MemoryStoreSpec.from_config`.

No mocks. Each test writes a real config.json and asks MemoryStoreSpec to
read it. OpenViking connection settings are intentionally out of scope.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rath.config.schema import LLMProviderConfig, MemoryProviderConfig
from rath.config.store import ConfigStore
from rath.memory.abc import MemoryStoreSpec


def _build_store_with(tmp_path: Path, **providers: MemoryProviderConfig) -> ConfigStore:
    cfg_path = tmp_path / "config.json"
    store = ConfigStore(path=cfg_path)
    for name, entry in providers.items():
        store.config.memory.providers[name] = entry
    store.save()
    return ConfigStore(path=cfg_path)


def test_named_memory_provider_round_trips_into_spec(tmp_path: Path) -> None:
    store = _build_store_with(
        tmp_path,
        main=MemoryProviderConfig(
            path="/tmp/my-memory",
            embedding_provider="embed-main",
            chat_provider="chat-main",
        ),
    )
    spec = MemoryStoreSpec.from_config("main", store=store)
    assert spec.options is not None
    assert spec.options["path"] == "/tmp/my-memory"
    assert spec.options["embedding_provider"] == "embed-main"
    assert spec.options["chat_provider"] == "chat-main"


def test_named_milvus_provider_round_trips_into_spec(tmp_path: Path) -> None:
    store = _build_store_with(
        tmp_path,
        main=MemoryProviderConfig(
            backend_kind="milvus",
            uri="http://localhost:19530",
            api_key="milvus-token",
            db_name="default",
            collection_name="openrath_memory",
            embedding_provider="embed-main",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=512,
            max_scan=2048,
        ),
    )
    spec = MemoryStoreSpec.from_config("main", store=store)
    assert spec.options is not None
    assert spec.options["uri"] == "http://localhost:19530"
    assert spec.options["token"] == "milvus-token"
    assert spec.options["db_name"] == "default"
    assert spec.options["collection_name"] == "openrath_memory"
    assert spec.options["embedding_provider"] == "embed-main"
    assert spec.options["embedding_model"] == "text-embedding-3-small"
    assert spec.options["embedding_dimensions"] == 512
    assert spec.options["max_scan"] == 2048


def test_default_memory_provider_used_when_name_omitted(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    store = ConfigStore(path=cfg_path)
    store.config.memory.default_provider = "local-default"
    store.config.memory.providers["local-default"] = MemoryProviderConfig(
        embedding_provider="embed",
    )
    store.save()
    reloaded = ConfigStore(path=cfg_path)
    spec = MemoryStoreSpec.from_config(None, store=reloaded)
    assert spec.options is not None
    assert spec.options["embedding_provider"] == "embed"


def test_explicit_overrides_win(tmp_path: Path) -> None:
    store = _build_store_with(
        tmp_path,
        main=MemoryProviderConfig(embedding_provider="from-config"),
    )
    spec = MemoryStoreSpec.from_config(
        "main",
        store=store,
        namespace="override-ns",
    )
    assert spec.namespace == "override-ns"
    assert spec.options is not None
    assert spec.options["embedding_provider"] == "from-config"


def test_unknown_name_raises_with_available_listed(tmp_path: Path) -> None:
    store = _build_store_with(
        tmp_path,
        alpha=MemoryProviderConfig(),
        beta=MemoryProviderConfig(),
    )
    with pytest.raises(KeyError) as exc_info:
        MemoryStoreSpec.from_config("gamma", store=store)
    msg = str(exc_info.value)
    assert "gamma" in msg
    assert "alpha" in msg
    assert "beta" in msg


def test_missing_default_provider_raises_clearly(tmp_path: Path) -> None:
    store = ConfigStore(path=tmp_path / "config.json")
    with pytest.raises(KeyError, match="no memory provider name"):
        MemoryStoreSpec.from_config(None, store=store)


def test_agent_resolves_config_provider_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``Agent(memory='preset')`` opens via config when the name is registered."""
    import rath.memory.registry as reg
    from rath.flow.agent import Agent
    from rath.llm import Provider
    from rath.memory.adapters.local import LocalMemoryBackend

    # Earlier tests may have cleared the registry via ``_reset()``.
    reg._REGISTRY["local"] = LocalMemoryBackend
    reg.set_default("local")

    home = tmp_path / "openrath_home"
    monkeypatch.setenv("OPENRATH_HOME", str(home))
    store = ConfigStore(path=home / "config.json")
    store.config.llm.providers["chat"] = LLMProviderConfig(
        provider_kind="openai",
        model="gpt-test",
        api_key="sk-test",
    )
    store.config.memory.providers["preset"] = MemoryProviderConfig(
        embedding_provider="chat",
    )
    store.save()

    agent = Agent(
        "You are helpful.", provider=Provider(model="gpt-test"), memory="preset"
    )
    try:
        assert agent.memory is not None
        assert agent.memory.spec is not None
        opts = agent.memory.spec.options or {}
        assert opts.get("embedding_provider") == "chat"
    finally:
        agent.close()
