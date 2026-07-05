"""P4.2 — AgentParam.to() rebinds the provider (type-dispatched, chainable).

- ``ap.to(Provider(...))`` rebinds .provider to that value;
- ``ap.to(provider="name")`` resolves lazily via Provider.from_config;
- ``ap.to(model="m")`` overrides just the model on the current provider;
- returns self (chainable);
- a bare non-Provider positional is rejected (str stays reserved for sandbox
  semantics elsewhere; here the LLM path requires Provider/provider=/model=).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from rath.config.paths import resolve_config_path
from rath.config.schema import LLMProviderConfig
from rath.config.store import ConfigStore
from rath.flow.agent_param import AgentParam
from rath.llm.provider import Provider
from rath.session.session import Session


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("OPENRATH_HOME", str(tmp_path / "home"))
    ConfigStore._cache.clear()
    yield
    ConfigStore._cache.clear()


def _ap() -> AgentParam:
    return AgentParam(
        agent_session=Session.from_agent_prompt("sys"),
        provider=Provider(model="base"),
    )


def test_to_provider_instance() -> None:
    ap = _ap()
    ret = ap.to(Provider(model="gpt-5.5", api_key="sk-x"))
    assert ret is ap  # chainable
    assert ap.provider.model == "gpt-5.5"
    assert ap.provider.api_key == "sk-x"


def test_to_provider_name_from_config() -> None:
    store = ConfigStore(path=resolve_config_path())
    store.config.llm.providers["main"] = LLMProviderConfig(
        provider_kind="anthropic", model="claude", api_key="sk-cfg"
    )
    store.config.llm.default_provider = "main"
    store.save()
    ConfigStore._cache.clear()

    ap = _ap()
    ap.to(provider="main")
    assert ap.provider.model == "claude"
    assert ap.provider.provider_kind == "anthropic"
    assert ap.provider.api_key == "sk-cfg"


def test_to_model_override_keeps_other_fields() -> None:
    ap = AgentParam(
        agent_session=Session.from_agent_prompt("sys"),
        provider=Provider(model="old", api_key="sk-keep", temperature=0.3),
    )
    ap.to(model="new")
    assert ap.provider.model == "new"
    assert ap.provider.api_key == "sk-keep"
    assert ap.provider.temperature == 0.3


def test_to_rejects_bare_string() -> None:
    ap = _ap()
    with pytest.raises(TypeError):
        ap.to("openai")  # ambiguous; must use provider= or Provider(...)


def test_to_requires_something() -> None:
    ap = _ap()
    with pytest.raises((TypeError, ValueError)):
        ap.to()
