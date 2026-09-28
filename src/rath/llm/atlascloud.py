"""Atlas Cloud OpenAI-compatible adapter registration."""

from __future__ import annotations

from dataclasses import replace

from rath.config.env import env_value
from rath.llm.credentials import resolve_credential
from rath.llm.openai.client import RathOpenAIChatClient
from rath.llm.provider import Provider
from rath.llm.registry import register_chat_client

ATLASCLOUD_BASE_URL = "https://api.atlascloud.ai/v1"
ATLASCLOUD_DEFAULT_MODEL = "qwen/qwen3.5-flash"


def bind_atlascloud_provider(provider: Provider) -> Provider:
    """Fill Atlas Cloud defaults before using the OpenAI-compatible client."""
    return replace(
        provider,
        provider_kind="openai",
        base_url=provider.base_url or ATLASCLOUD_BASE_URL,
        api_key=resolve_atlascloud_api_key(provider),
        model=provider.model or env_value("ATLASCLOUD_DEFAULT_MODEL") or ATLASCLOUD_DEFAULT_MODEL,
    )


def resolve_atlascloud_api_key(provider: Provider) -> str:
    """Resolve Atlas Cloud credentials from Provider or env."""
    return resolve_credential(
        provider.api_key,
        env_value("ATLASCLOUD_API_KEY"),
        env_value("ATLAS_CLOUD_API_KEY"),
    )


def atlascloud_chat_client(provider: Provider) -> RathOpenAIChatClient:
    """Construct an OpenAI-compatible chat client configured for Atlas Cloud."""
    return RathOpenAIChatClient(bind_atlascloud_provider(provider))


register_chat_client("atlascloud", atlascloud_chat_client)


__all__ = [
    "ATLASCLOUD_BASE_URL",
    "ATLASCLOUD_DEFAULT_MODEL",
    "atlascloud_chat_client",
    "bind_atlascloud_provider",
    "resolve_atlascloud_api_key",
]
