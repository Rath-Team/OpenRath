"""P4.3 — Session carries an optional provider, switchable via .to().

- ``session.to("local", spec=...)`` still binds the SANDBOX (unchanged);
- ``session.to(Provider(...))`` sets a session-level provider (value, no
  lifecycle);
- ``session.to(provider="name")`` resolves a config preset lazily;
- the bound provider survives fork/detach (copied like sandbox_backend) and
  merge keeps self's provider;
- binding a provider must NOT open a sandbox.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from rath.config.paths import resolve_config_path
from rath.config.schema import LLMProviderConfig
from rath.config.store import ConfigStore
from rath.llm.provider import Provider
from rath.session.session import Session


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("OPENRATH_HOME", str(tmp_path / "home"))
    ConfigStore._cache.clear()
    yield
    ConfigStore._cache.clear()


def test_to_local_still_binds_sandbox_not_provider() -> None:
    s = Session.from_user_message("hi").to("local", spec="./")
    assert s.sandbox_backend == "local"
    assert s.provider is None  # provider untouched by a sandbox .to()


def test_to_provider_instance_sets_provider_no_sandbox_open() -> None:
    s = Session.from_user_message("hi").to(Provider(model="gpt-5.5", api_key="sk"))
    assert s.provider is not None and s.provider.model == "gpt-5.5"
    # No sandbox opened by binding a provider.
    assert s.sandbox is None


def test_to_provider_name_lazy_resolves() -> None:
    store = ConfigStore(path=resolve_config_path())
    store.config.llm.providers["main"] = LLMProviderConfig(
        provider_kind="openai", model="gpt-x", api_key="sk-cfg"
    )
    store.config.llm.default_provider = "main"
    store.save()
    ConfigStore._cache.clear()

    s = Session.from_user_message("hi").to(provider="main")
    assert s.provider is not None and s.provider.model == "gpt-x"


def test_chainable_sandbox_then_provider() -> None:
    s = (
        Session.from_user_message("hi")
        .to("local", spec="./")
        .to(Provider(model="m", api_key="sk"))
    )
    assert s.sandbox_backend == "local"
    assert s.provider is not None and s.provider.model == "m"


def test_provider_survives_fork_and_detach() -> None:
    s = Session.from_user_message("hi").to(Provider(model="m", api_key="sk"))
    f = s.fork()
    d = s.detach()
    assert f.provider is not None and f.provider.model == "m"
    assert d.provider is not None and d.provider.model == "m"


def test_merge_keeps_self_provider() -> None:
    a = Session.from_user_message("a").to(Provider(model="A", api_key="sk"))
    b = Session.from_user_message("b").to(Provider(model="B", api_key="sk"))
    merged = a.merge(b)
    assert merged.provider is not None and merged.provider.model == "A"


def test_default_provider_is_none() -> None:
    assert Session.from_user_message("x").provider is None
