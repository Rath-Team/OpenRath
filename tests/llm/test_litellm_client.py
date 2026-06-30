"""Unit tests for :mod:`rath.llm.litellm` adapter."""

from __future__ import annotations

from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest

from rath.llm import (
    ChatClient,
    Provider,
    StreamingChatClient,
    chat_client_for,
    registered_kinds,
)
from rath.llm.chat_request import RathLLMChatRequest, RathLLMMessage
from rath.llm.litellm import RathLiteLLMChatClient


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ensure no stray env vars affect tests."""
    for v in (
        "LITELLM_API_KEY",
        "LITELLM_API_BASE",
        "LITELLM_MODEL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(v, raising=False)
    yield


class TestRegistration:
    def test_litellm_in_registered_kinds(self) -> None:
        assert "litellm" in registered_kinds()

    def test_chat_client_for_dispatches_litellm(self) -> None:
        provider = Provider(provider_kind="litellm")
        client = chat_client_for(provider)
        assert isinstance(client, RathLiteLLMChatClient)


class TestProtocols:
    def test_litellm_client_is_chat_client(self) -> None:
        client = RathLiteLLMChatClient(Provider(provider_kind="litellm"))
        assert isinstance(client, ChatClient)

    def test_litellm_client_is_streaming(self) -> None:
        client = RathLiteLLMChatClient(Provider(provider_kind="litellm"))
        assert isinstance(client, StreamingChatClient)


class TestCredentialResolution:
    def test_api_key_from_provider(self) -> None:
        client = RathLiteLLMChatClient(
            Provider(provider_kind="litellm", api_key="pk-test")
        )
        assert client._api_key == "pk-test"

    def test_api_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LITELLM_API_KEY", "env-key")
        client = RathLiteLLMChatClient(Provider(provider_kind="litellm"))
        assert client._api_key == "env-key"

    def test_provider_key_takes_precedence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LITELLM_API_KEY", "env-key")
        client = RathLiteLLMChatClient(
            Provider(provider_kind="litellm", api_key="provider-key")
        )
        assert client._api_key == "provider-key"

    def test_no_key_is_none(self) -> None:
        client = RathLiteLLMChatClient(Provider(provider_kind="litellm"))
        assert client._api_key is None

    def test_base_url_from_provider(self) -> None:
        client = RathLiteLLMChatClient(
            Provider(provider_kind="litellm", base_url="http://localhost:4000")
        )
        assert client._api_base == "http://localhost:4000"

    def test_base_url_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LITELLM_API_BASE", "http://proxy:4000")
        client = RathLiteLLMChatClient(Provider(provider_kind="litellm"))
        assert client._api_base == "http://proxy:4000"


class TestComplete:
    @patch("rath.llm.litellm.client.litellm_completion")
    def test_complete_passes_drop_params(self, mock_completion: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "id": "test-id",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "hello"},
                }
            ],
            "created": 1234567890,
            "model": "gpt-4o-mini",
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }
        mock_completion.return_value = mock_response

        client = RathLiteLLMChatClient(
            Provider(provider_kind="litellm", model="openai/gpt-4o-mini")
        )
        req = RathLLMChatRequest(
            messages=(RathLLMMessage(role="user", content="hi"),),
        )
        client.complete(req)

        call_kwargs = mock_completion.call_args[1]
        assert call_kwargs["drop_params"] is True

    @patch("rath.llm.litellm.client.litellm_completion")
    def test_complete_passes_api_key(self, mock_completion: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "id": "test-id",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "ok"},
                }
            ],
            "created": 1234567890,
            "model": "openai/gpt-4o-mini",
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 1,
                "total_tokens": 6,
            },
        }
        mock_completion.return_value = mock_response

        client = RathLiteLLMChatClient(
            Provider(
                provider_kind="litellm",
                model="openai/gpt-4o-mini",
                api_key="sk-test",
            )
        )
        req = RathLLMChatRequest(
            messages=(RathLLMMessage(role="user", content="hi"),),
        )
        client.complete(req)

        call_kwargs = mock_completion.call_args[1]
        assert call_kwargs["api_key"] == "sk-test"

    @patch("rath.llm.litellm.client.litellm_completion")
    def test_complete_passes_api_base(self, mock_completion: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "id": "test-id",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "ok"},
                }
            ],
            "created": 1234567890,
            "model": "openai/gpt-4o-mini",
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 1,
                "total_tokens": 6,
            },
        }
        mock_completion.return_value = mock_response

        client = RathLiteLLMChatClient(
            Provider(
                provider_kind="litellm",
                model="openai/gpt-4o-mini",
                base_url="http://localhost:4000",
            )
        )
        req = RathLLMChatRequest(
            messages=(RathLLMMessage(role="user", content="hi"),),
        )
        client.complete(req)

        call_kwargs = mock_completion.call_args[1]
        assert call_kwargs["api_base"] == "http://localhost:4000"

    @patch("rath.llm.litellm.client.litellm_completion")
    def test_complete_returns_normalized_response(
        self, mock_completion: MagicMock
    ) -> None:
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "id": "chatcmpl-123",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "pong",
                    },
                }
            ],
            "created": 1234567890,
            "model": "openai/gpt-4o-mini",
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 1,
                "total_tokens": 11,
            },
        }
        mock_completion.return_value = mock_response

        client = RathLiteLLMChatClient(
            Provider(provider_kind="litellm", model="openai/gpt-4o-mini")
        )
        req = RathLLMChatRequest(
            messages=(RathLLMMessage(role="user", content="ping"),),
        )
        resp = client.complete(req)

        assert resp.id == "chatcmpl-123"
        assert resp.primary_choice.message.content == "pong"
        assert resp.usage is not None
        assert resp.usage.total_tokens == 11


class TestCompleteStream:
    @patch("rath.llm.litellm.client.litellm_completion")
    def test_stream_passes_drop_params(self, mock_completion: MagicMock) -> None:
        mock_completion.return_value = iter([])

        client = RathLiteLLMChatClient(
            Provider(provider_kind="litellm", model="openai/gpt-4o-mini")
        )
        req = RathLLMChatRequest(
            messages=(RathLLMMessage(role="user", content="hi"),),
        )
        list(client.complete_stream(req))

        call_kwargs = mock_completion.call_args[1]
        assert call_kwargs["drop_params"] is True
        assert call_kwargs["stream"] is True
