"""P1.1 — split secrets (api_key) out of config.json into credentials.json.

Real filesystem tests. The in-memory ``RathConfig`` model is unchanged
(``entry.api_key`` still works for callers); the split happens only at the
ConfigStore load/save boundary:

- ``save()`` writes routing/presets to ``config.json`` (no api_key) and
  secrets to a 0600 ``credentials.json``;
- ``load()`` merges them back so ``entry.api_key`` is populated;
- an existing single ``config.json`` with inline ``api_key`` still loads
  (back-compat) and is migrated out to ``credentials.json`` on the next save.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterator

import pytest

from rath.config.paths import resolve_config_dir, resolve_config_path
from rath.config.schema import LLMProviderConfig
from rath.config.store import ConfigStore


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    ConfigStore._cache.clear()
    yield
    ConfigStore._cache.clear()


def _credentials_path() -> Path:
    return resolve_config_dir() / "credentials.json"


def test_save_writes_secret_to_credentials_not_config(
    _isolate_openrath_home: Path,
) -> None:
    store = ConfigStore(path=resolve_config_path())
    store.config.llm.providers["main"] = LLMProviderConfig(
        provider_kind="openai", model="gpt-5", api_key="sk-secret-xyz"
    )
    store.config.llm.default_provider = "main"
    store.save()

    config_raw = json.loads(resolve_config_path().read_text(encoding="utf-8"))
    main_entry = config_raw["llm"]["providers"]["main"]
    # Routing fields stay; the secret must NOT be in config.json.
    assert main_entry["model"] == "gpt-5"
    assert main_entry.get("api_key") in (None, "")

    creds_raw = json.loads(_credentials_path().read_text(encoding="utf-8"))
    # Secret lives in credentials.json, addressable by the provider name.
    assert "sk-secret-xyz" in json.dumps(creds_raw)


def test_load_remerges_secret(_isolate_openrath_home: Path) -> None:
    store = ConfigStore(path=resolve_config_path())
    store.config.llm.providers["main"] = LLMProviderConfig(
        provider_kind="openai", model="gpt-5", api_key="sk-remerge"
    )
    store.config.llm.default_provider = "main"
    store.save()
    ConfigStore._cache.clear()

    reloaded = ConfigStore.load()
    assert reloaded.get_llm_provider("main").api_key == "sk-remerge"


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX perms only")
def test_credentials_file_is_0600(_isolate_openrath_home: Path) -> None:
    store = ConfigStore(path=resolve_config_path())
    store.config.llm.providers["main"] = LLMProviderConfig(
        provider_kind="openai", api_key="sk-perm"
    )
    store.save()
    assert (_credentials_path().stat().st_mode & 0o777) == 0o600


def test_legacy_inline_api_key_still_loads_and_migrates(
    _isolate_openrath_home: Path,
) -> None:
    # Hand-write a legacy single-file config with an inline secret.
    path = resolve_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "llm": {
                    "default_provider": "main",
                    "providers": {
                        "main": {
                            "provider_kind": "openai",
                            "model": "gpt-5",
                            "api_key": "sk-legacy-inline",
                        }
                    },
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Loads with the inline secret intact (back-compat).
    store = ConfigStore.load()
    assert store.get_llm_provider("main").api_key == "sk-legacy-inline"

    # On save, the secret migrates out to credentials.json and leaves
    # config.json clean.
    store.save()
    config_raw = json.loads(path.read_text(encoding="utf-8"))
    assert config_raw["llm"]["providers"]["main"].get("api_key") in (None, "")
    creds_raw = json.loads(_credentials_path().read_text(encoding="utf-8"))
    assert "sk-legacy-inline" in json.dumps(creds_raw)


def test_inline_key_takes_precedence_over_credentials(
    _isolate_openrath_home: Path,
) -> None:
    """If both an inline key and a credentials entry exist, inline wins
    (highest precedence, matches the documented back-compat rule)."""
    path = resolve_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "llm": {
                    "default_provider": "main",
                    "providers": {
                        "main": {"provider_kind": "openai", "api_key": "sk-inline"}
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    _credentials_path().write_text(
        json.dumps({"version": 1, "llm": {"providers": {"main": "sk-from-creds"}}}),
        encoding="utf-8",
    )
    store = ConfigStore.load()
    assert store.get_llm_provider("main").api_key == "sk-inline"
