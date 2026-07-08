"""P4.5 — Workflow.to() fans a provider out to all registered AgentParams."""

from __future__ import annotations

import pytest

from rath.flow.agent_param import AgentParam
from rath.flow.workflow import Workflow
from rath.llm.provider import Provider
from rath.session.session import Session


class _TwoAgents(Workflow):
    def __init__(self) -> None:
        super().__init__()
        self.a = AgentParam(Session.from_agent_prompt("a"), Provider(model="a0"))
        self.b = AgentParam(Session.from_agent_prompt("b"), Provider(model="b0"))


def test_to_provider_rebinds_all_agents() -> None:
    wf = _TwoAgents()
    ret = wf.to(Provider(model="shared", api_key="sk"))
    assert ret is wf  # chainable
    for _name, ap in wf.named_agents():
        assert ap.provider.model == "shared"


def test_to_provider_name_rebinds_all(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OPENRATH_HOME", str(tmp_path / "home"))
    from rath.config.paths import resolve_config_path
    from rath.config.schema import LLMProviderConfig
    from rath.config.store import ConfigStore

    ConfigStore._cache.clear()
    store = ConfigStore(path=resolve_config_path())
    store.config.llm.providers["main"] = LLMProviderConfig(
        provider_kind="openai", model="cfg-model", api_key="sk"
    )
    store.config.llm.default_provider = "main"
    store.save()
    ConfigStore._cache.clear()

    wf = _TwoAgents()
    wf.to(provider="main")
    for _name, ap in wf.named_agents():
        assert ap.provider.model == "cfg-model"


def test_to_model_override_all() -> None:
    wf = _TwoAgents()
    wf.to(model="m9")
    for _name, ap in wf.named_agents():
        assert ap.provider.model == "m9"


def test_to_on_empty_workflow_is_noop() -> None:
    class _Empty(Workflow):
        pass

    wf = _Empty()
    assert wf.to(Provider(model="x", api_key="sk")) is wf  # no agents, no error


def test_to_rejects_bare_string() -> None:
    wf = _TwoAgents()
    with pytest.raises(TypeError):
        wf.to("openai")
