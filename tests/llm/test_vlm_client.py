"""Integration tests for :class:`RathOpenAIVLMClient` (no mocks).

Real GLM-4.6v calls against the configured OpenAI-compatible endpoint.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest

from rath.llm import RathOpenAIVLMClient, VLMProvider

_HAS_LIVE_KEY = len(os.environ.get("OPENAI_API_KEY", "").strip()) >= 8
_live_only = pytest.mark.skipif(
    not _HAS_LIVE_KEY,
    reason="OPENAI_API_KEY not set or too short (live API tests)",
)


# 1x1 red PNG — smallest possible valid PNG; we cannot assert what the VLM
# returns for it (model-dependent), but we *can* assert the call shape works
# (response is a non-empty string) and the SDK accepts our content format.
_TINY_RED_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIA"
    "X8jx0gAAAABJRU5ErkJggg=="
)


@pytest.fixture
def provider() -> VLMProvider:
    api_key = os.environ["OPENAI_API_KEY"].strip()
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    model = os.environ.get("OPENAI_VLM_MODEL", "").strip() or "glm-4.6v"
    return VLMProvider(api_key=api_key, base_url=base_url, model=model)


@pytest.fixture
def client(provider: VLMProvider) -> RathOpenAIVLMClient:
    return RathOpenAIVLMClient(provider)


@_live_only
@pytest.mark.live_llm
def test_describe_image_bytes_returns_non_empty_caption(
    client: RathOpenAIVLMClient,
) -> None:
    caption = client.describe(_TINY_RED_PNG, prompt="Describe this image briefly.")
    assert isinstance(caption, str)
    assert caption.strip(), "caption must be non-empty"


@_live_only
@pytest.mark.live_llm
def test_describe_path_reads_file_and_returns_caption(
    client: RathOpenAIVLMClient,
    tmp_path: Path,
) -> None:
    img_path = tmp_path / "tiny.png"
    img_path.write_bytes(_TINY_RED_PNG)
    caption = client.describe_path(img_path, prompt="What color dominates?")
    assert isinstance(caption, str)
    assert caption.strip()


def test_provider_from_config_uses_vlm_provider_entry(tmp_path: Path) -> None:
    from rath.config.schema import (
        LLMConfig,
        LLMProviderConfig,
        RathConfig,
    )
    from rath.config.store import ConfigStore

    cfg = RathConfig(
        llm=LLMConfig(
            default_provider="chat",
            vlm_provider="vision",
            providers={
                "chat": LLMProviderConfig(
                    provider_kind="openai",
                    api_key="sk-chat",
                    base_url="https://chat.example/v1",
                    model="gpt-x",
                ),
                "vision": LLMProviderConfig(
                    provider_kind="openai",
                    api_key="sk-vis",
                    base_url="https://vision.example/v1",
                    model="glm-4.6v",
                ),
            },
        ),
    )
    store = ConfigStore(path=tmp_path / "config.json")
    store._data = cfg
    prov = VLMProvider.from_config(store=store)
    assert prov.api_key == "sk-vis"
    assert prov.base_url == "https://vision.example/v1"
    assert prov.model == "glm-4.6v"


def test_provider_from_config_raises_when_no_vlm_or_default(tmp_path: Path) -> None:
    """VLM has no safe default model, so missing config must raise."""
    from rath.config.schema import LLMConfig, RathConfig
    from rath.config.store import ConfigStore

    cfg = RathConfig(llm=LLMConfig(providers={}))
    store = ConfigStore(path=tmp_path / "config.json")
    store._data = cfg
    with pytest.raises(KeyError):
        VLMProvider.from_config(store=store)
