"""Unit tests for :mod:`rath.llm.registry` dispatch."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterator, cast

import pytest

from rath.llm import (
    Provider,
    RathAnthropicChatClient,
    RathLLMChatRequest,
    RathLLMChatResponse,
    RathOpenAIChatClient,
    chat_client_for,
    register_chat_client,
    registered_kinds,
)


@pytest.fixture(autouse=True)
def _stub_credentials(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Both built-in clients require an api key to construct; supply dummies."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-anthropic")
    monkeypatch.setenv("ATLASCLOUD_API_KEY", "test-key-atlascloud")
    # Make sure no leftover env-var base_url steers Azure routing.
    for v in (
        "OPENAI_BASE_URL",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_API_KEY",
    ):
        monkeypatch.delenv(v, raising=False)
    yield


def test_default_provider_kind_is_openai() -> None:
    client = chat_client_for(Provider())
    assert isinstance(client, RathOpenAIChatClient)


def test_explicit_openai_provider_kind() -> None:
    client = chat_client_for(Provider(provider_kind="openai"))
    assert isinstance(client, RathOpenAIChatClient)


def test_anthropic_provider_kind() -> None:
    client = chat_client_for(Provider(provider_kind="anthropic"))
    assert isinstance(client, RathAnthropicChatClient)


def test_atlascloud_provider_kind_uses_openai_compatible_client() -> None:
    client = chat_client_for(Provider(provider_kind="atlascloud"))
    assert isinstance(client, RathOpenAIChatClient)
    assert client.provider.provider_kind == "openai"
    assert client.provider.base_url == "https://api.atlascloud.ai/v1"
    assert client.provider.model == "qwen/qwen3.5-flash"
    assert client._client.api_key == "test-key-atlascloud"


def test_unknown_provider_kind_raises_value_error() -> None:
    # ``provider_kind`` is typed as a Literal but the registry must still
    # produce a useful runtime error for callers that bypass the type.
    bogus = cast(Provider, replace(Provider(), provider_kind=cast("str", "imaginary")))
    with pytest.raises(ValueError, match="unknown provider_kind"):
        chat_client_for(bogus)


def test_register_chat_client_extends_dispatch() -> None:
    class DummyClient:
        def __init__(self, provider: Provider) -> None:
            self._provider = provider

        @property
        def provider(self) -> Provider:
            return self._provider

        def complete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
            raise NotImplementedError

    register_chat_client("dummy-test", DummyClient)
    assert "dummy-test" in registered_kinds()

    bogus = cast(Provider, replace(Provider(), provider_kind=cast("str", "dummy-test")))
    client = chat_client_for(bogus)
    assert isinstance(client, DummyClient)


def test_builtin_kinds_are_registered_on_import() -> None:
    kinds = registered_kinds()
    assert "openai" in kinds
    assert "anthropic" in kinds
