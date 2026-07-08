"""P5.4 — CompiledWorkflow.validate() pre-flight (offline, no model call).

validate() inspects the manifest and fails fast on unknown provider kinds or
missing credentials BEFORE any run. It returns a list of problems (empty when
clean); validate(raise_on_error=True) raises instead. No network / no live LLM.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from rath.flow.agent_param import AgentParam
from rath.flow.workflow import Workflow
from rath.llm.provider import Provider
from rath.session.session import Session


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("OPENRATH_HOME", str(tmp_path / "home"))
    for v in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    yield


class _One(Workflow):
    def __init__(self, provider: Provider) -> None:
        super().__init__()
        self.a = AgentParam(Session.from_agent_prompt("sys"), provider)


def test_validate_clean_when_key_present() -> None:
    wf = _One(Provider(provider_kind="openai", model="m", api_key="sk-explicit"))
    problems = wf.compile().validate()
    assert problems == []


def test_validate_flags_missing_credentials() -> None:
    # No explicit key and no env/config → credential problem.
    wf = _One(Provider(provider_kind="openai", model="m"))
    problems = wf.compile().validate()
    assert any("credential" in p.lower() or "api" in p.lower() for p in problems)


def test_validate_flags_unknown_provider_kind() -> None:
    wf = _One(Provider(provider_kind="openai", model="m", api_key="sk"))
    cw = wf.compile()
    # Corrupt the manifest to an unregistered kind to exercise the check.
    from dataclasses import replace

    cw.manifest.agents[0] = replace(
        cw.manifest.agents[0],
        provider=Provider(provider_kind="nope-kind", model="m", api_key="sk"),  # type: ignore[arg-type]
    )
    problems = cw.validate()
    assert any("kind" in p.lower() for p in problems)


def test_validate_raise_on_error() -> None:
    wf = _One(Provider(provider_kind="openai", model="m"))
    with pytest.raises(ValueError):
        wf.compile().validate(raise_on_error=True)
