"""P2.2/P2.3 — credential resolution routes through the EnvSpec registry.

Characterization tests: they pin the documented precedence (Provider field >
env > config) for each sync client's resolver, so the refactor from bare
``os.environ.get`` to ``env_value`` is provably behavior-preserving. No mocks
— we call the real module-level resolver functions with real env state.
"""

from __future__ import annotations

import pytest

from rath.llm.provider import Provider


@pytest.fixture(autouse=True)
def _isolate_home(monkeypatch: pytest.MonkeyPatch, tmp_path):  # type: ignore[no-untyped-def]
    # Pin OPENRATH_HOME to an empty tmp dir so config-file fallback is inert
    # and we're testing only the Provider>env tiers.
    monkeypatch.setenv("OPENRATH_HOME", str(tmp_path / "home"))
    yield


def test_openai_base_url_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    from rath.llm.openai.client import _resolve_base_url

    monkeypatch.setenv("OPENAI_BASE_URL", "https://env.example/v1")
    # Provider field wins.
    assert (
        _resolve_base_url(Provider(base_url="https://explicit/v1"))
        == "https://explicit/v1"
    )
    # Falls through to env.
    assert _resolve_base_url(Provider()) == "https://env.example/v1"
    # Whitespace env is treated as unset.
    monkeypatch.setenv("OPENAI_BASE_URL", "   ")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://azure.example")
    assert _resolve_base_url(Provider()) == "https://azure.example"


def test_openai_api_key_precedence_non_azure(monkeypatch: pytest.MonkeyPatch) -> None:
    from rath.llm.openai.client import _resolve_api_key

    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    assert _resolve_api_key(Provider(api_key="sk-explicit"), "") == "sk-explicit"
    assert _resolve_api_key(Provider(), "https://api.openai.com/v1") == "sk-env"


def test_openai_api_key_precedence_azure(monkeypatch: pytest.MonkeyPatch) -> None:
    from rath.llm.openai.client import _resolve_api_key

    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azkey")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    # Azure endpoint prefers the Azure key.
    assert _resolve_api_key(Provider(), "https://x.openai.azure.com/openai") == "azkey"


def test_anthropic_key_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    from rath.llm.anthropic.client import _resolve_anthropic_key

    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak-env")
    assert _resolve_anthropic_key(Provider(api_key="ak-explicit")) == "ak-explicit"
    assert _resolve_anthropic_key(Provider()) == "ak-env"


def test_litellm_key_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("litellm")
    from rath.llm.litellm.client import _resolve_litellm_key

    monkeypatch.setenv("LITELLM_API_KEY", "lk-env")
    assert _resolve_litellm_key(Provider(api_key="lk-explicit")) == "lk-explicit"
    assert _resolve_litellm_key(Provider()) == "lk-env"
