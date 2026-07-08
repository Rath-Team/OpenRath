"""P3.3 — ConfigStore writes/validates the root manifest at the data root."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest

from rath.config.paths import resolve_config_dir, resolve_config_path
from rath.config.schema import LLMProviderConfig
from rath.config.store import ConfigStore
from rath.persistence.manifest import LAYOUT_VERSION, MANIFEST_FILENAME


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    ConfigStore._cache.clear()
    yield
    ConfigStore._cache.clear()


def test_save_creates_manifest(_isolate_openrath_home: Path) -> None:
    store = ConfigStore(path=resolve_config_path())
    store.config.llm.providers["m"] = LLMProviderConfig(provider_kind="openai")
    store.save()
    manifest_path = resolve_config_dir() / MANIFEST_FILENAME
    assert manifest_path.is_file()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["layout_version"] == LAYOUT_VERSION


def test_load_raises_on_newer_layout(_isolate_openrath_home: Path) -> None:
    store = ConfigStore(path=resolve_config_path())
    store.config.llm.providers["m"] = LLMProviderConfig(provider_kind="openai")
    store.save()
    manifest_path = resolve_config_dir() / MANIFEST_FILENAME
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["layout_version"] = LAYOUT_VERSION + 1
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    ConfigStore._cache.clear()

    from rath.persistence.manifest import ManifestVersionError

    with pytest.raises(ManifestVersionError):
        ConfigStore.load()
