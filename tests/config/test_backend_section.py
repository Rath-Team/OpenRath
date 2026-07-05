"""P1.2 — a ``backend`` config section parallel to llm / memory / mcp.

Gives backends (e.g. opensandbox) a config home instead of env-only. Also
verifies the backend section's ``api_key`` participates in the P1.1 secret
split (credentials.json), since ``backend`` is in ``SECRET_SECTIONS``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest

from rath.config.paths import resolve_config_dir, resolve_config_path
from rath.config.schema import BackendProviderConfig, RathConfig
from rath.config.store import ConfigStore


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    ConfigStore._cache.clear()
    yield
    ConfigStore._cache.clear()


def test_backend_section_roundtrips(_isolate_openrath_home: Path) -> None:
    store = ConfigStore(path=resolve_config_path())
    store.config.backend.providers["sandbox-main"] = BackendProviderConfig(
        backend_kind="opensandbox",
        domain="https://sandbox.example.com",
        api_key="sk-backend-secret",
    )
    store.config.backend.default_provider = "sandbox-main"
    store.save()
    ConfigStore._cache.clear()

    reloaded = ConfigStore.load()
    entry = reloaded.get_backend_provider("sandbox-main")
    assert entry.backend_kind == "opensandbox"
    assert entry.domain == "https://sandbox.example.com"
    assert entry.api_key == "sk-backend-secret"


def test_backend_getter_unknown_name_lists_available(
    _isolate_openrath_home: Path,
) -> None:
    store = ConfigStore(path=resolve_config_path())
    store.config.backend.providers["a"] = BackendProviderConfig(
        backend_kind="opensandbox"
    )
    store.save()
    ConfigStore._cache.clear()
    reloaded = ConfigStore.load()
    with pytest.raises(KeyError, match="available"):
        reloaded.get_backend_provider("nope")


def test_backend_default_provider(_isolate_openrath_home: Path) -> None:
    store = ConfigStore(path=resolve_config_path())
    store.config.backend.providers["d"] = BackendProviderConfig(
        backend_kind="opensandbox", domain="https://d.example"
    )
    store.config.backend.default_provider = "d"
    store.save()
    ConfigStore._cache.clear()
    reloaded = ConfigStore.load()
    assert reloaded.get_backend_provider(None).domain == "https://d.example"


def test_backend_api_key_split_into_credentials(
    _isolate_openrath_home: Path,
) -> None:
    store = ConfigStore(path=resolve_config_path())
    store.config.backend.providers["s"] = BackendProviderConfig(
        backend_kind="opensandbox", api_key="sk-be-split"
    )
    store.save()

    config_raw = json.loads(resolve_config_path().read_text(encoding="utf-8"))
    assert config_raw["backend"]["providers"]["s"].get("api_key") in (None, "")
    creds_raw = json.loads(
        (resolve_config_dir() / "credentials.json").read_text(encoding="utf-8")
    )
    assert creds_raw["backend"]["providers"]["s"] == "sk-be-split"


def test_backend_section_defaults_empty() -> None:
    cfg = RathConfig()
    assert cfg.backend.providers == {}
    assert cfg.backend.default_provider is None
