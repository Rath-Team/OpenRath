"""P2.5 — opensandbox resolves domain/flags through the registry + backend config.

Closes the gap left by P1.2/P2: the `backend` config section had no consumer
and opensandbox read bare os.environ. These are offline, real-filesystem tests
of the pure resolver + is_available (no container, no live service).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from rath.backend.opensandbox import (
    resolve_opensandbox_domain,
    strict_workspace_bind,
)
from rath.config.paths import resolve_config_path
from rath.config.schema import BackendProviderConfig
from rath.config.store import ConfigStore


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("OPENRATH_HOME", str(tmp_path / "home"))
    for var in (
        "OPEN_SANDBOX_DOMAIN",
        "OPENSANDBOX_DOMAIN",
        "RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND",
    ):
        monkeypatch.delenv(var, raising=False)
    ConfigStore._cache.clear()
    yield
    ConfigStore._cache.clear()


def test_domain_env_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPEN_SANDBOX_DOMAIN", "https://env.example")
    assert resolve_opensandbox_domain() == "https://env.example"


def test_domain_legacy_env_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENSANDBOX_DOMAIN", "https://legacy.example")
    assert resolve_opensandbox_domain() == "https://legacy.example"


def test_domain_from_backend_config() -> None:
    """The backend config section is actually consumed (P1.2 wiring)."""
    store = ConfigStore(path=resolve_config_path())
    store.config.backend.providers["sb"] = BackendProviderConfig(
        backend_kind="opensandbox", domain="https://cfg.example"
    )
    store.config.backend.default_provider = "sb"
    store.save()
    ConfigStore._cache.clear()
    assert resolve_opensandbox_domain() == "https://cfg.example"


def test_domain_env_beats_config(monkeypatch: pytest.MonkeyPatch) -> None:
    store = ConfigStore(path=resolve_config_path())
    store.config.backend.providers["sb"] = BackendProviderConfig(
        backend_kind="opensandbox", domain="https://cfg.example"
    )
    store.config.backend.default_provider = "sb"
    store.save()
    ConfigStore._cache.clear()
    monkeypatch.setenv("OPEN_SANDBOX_DOMAIN", "https://env.example")
    assert resolve_opensandbox_domain() == "https://env.example"


def test_domain_none_when_unset() -> None:
    assert resolve_opensandbox_domain() is None


def test_strict_flag_read_at_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flag is resolved via the registry at call time (not frozen at import)."""
    assert strict_workspace_bind() is False
    monkeypatch.setenv("RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND", "1")
    assert strict_workspace_bind() is True
    monkeypatch.setenv("RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND", "no")
    assert strict_workspace_bind() is False
