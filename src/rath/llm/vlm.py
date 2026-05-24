"""Synchronous OpenAI-compatible vision (VLM) client.

The OpenAI chat completions endpoint accepts vision input via multimodal
content blocks (``{"type": "image_url", "image_url": {"url": ...}}``);
this module wraps that pattern in a small, focused interface so memory
adapters and other callers can hand off an image (bytes or path) and get
back a textual description.

The client is deliberately *not* part of :class:`Provider` — VLM and chat
endpoints frequently live under different model namespaces (e.g. GLM
splits ``glm-5.x`` chat from ``glm-4.6v`` vision), and the credentials
may differ.
"""

from __future__ import annotations

import base64
import mimetypes
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

from rath.llm.credentials import resolve_credential
from rath.llm.retry import retry_with_backoff

if TYPE_CHECKING:
    from rath.config.store import ConfigStore

__all__ = ["VLMProvider", "RathOpenAIVLMClient"]


_VLM_RETRYABLE: tuple[type[BaseException], ...] = (
    RateLimitError,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
)


@dataclass(frozen=True, kw_only=True, slots=True)
class VLMProvider:
    """Routing + credentials for an OpenAI-compatible vision endpoint."""

    model: str
    base_url: str | None = None
    api_key: str | None = None
    max_tokens: int | None = 512
    temperature: float | None = None
    retry_max_attempts: int | None = None
    retry_base_seconds: float | None = None

    def __str__(self) -> str:
        return self.model

    def __repr__(self) -> str:
        return self.__str__()

    @classmethod
    def from_config(
        cls,
        name: str | None = None,
        *,
        store: "ConfigStore | None" = None,
        **overrides: Any,
    ) -> "VLMProvider":
        """Build a :class:`VLMProvider` from ``~/.openrath/config.json``.

        Lookup order:

        1. ``name`` if given.
        2. ``llm.vlm_provider`` if set.

        Unlike :class:`EmbeddingProvider`, there is **no fallback** to
        ``llm.default_provider``: a chat model is rarely a vision model,
        and silently falling back would produce confusing 400 errors at
        first use. Raises :class:`KeyError` instead.
        """
        from rath.config.store import ConfigStore

        s = store or ConfigStore.load()
        if name is None:
            target = getattr(s.config.llm, "vlm_provider", None)
            if target is None:
                raise KeyError(
                    "no VLM provider configured: set llm.vlm_provider in "
                    f"{s.path} or pass name= explicitly",
                )
        else:
            target = name

        entry = s.get_llm_provider(target)
        if not entry.model:
            raise KeyError(
                f"VLM provider {target!r} has no model set; vision endpoints "
                "have no safe default — configure it in the config file",
            )
        base = cls(
            model=entry.model,
            api_key=entry.api_key,
            base_url=entry.base_url,
        )
        if not overrides:
            return base
        return replace(base, **overrides)


def _resolve_api_key(provider: VLMProvider) -> str:
    return resolve_credential(
        provider.api_key,
        os.environ.get("OPENAI_API_KEY"),
    )


def _resolve_base_url(provider: VLMProvider) -> str:
    return resolve_credential(
        provider.base_url,
        os.environ.get("OPENAI_BASE_URL"),
    )


def _data_url(image_bytes: bytes, mime: str) -> str:
    payload = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{payload}"


def _infer_mime(path: Path) -> str:
    guess, _ = mimetypes.guess_type(path.name)
    return guess or "application/octet-stream"


class RathOpenAIVLMClient:
    """Thin wrapper turning ``(image, prompt) -> caption`` into a chat call."""

    def __init__(self, provider: VLMProvider) -> None:
        key = _resolve_api_key(provider)
        if not key:
            raise ValueError(
                "No API key for VLMProvider: set VLMProvider.api_key, export "
                "OPENAI_API_KEY, or configure llm.vlm_provider in "
                "~/.openrath/config.json.",
            )
        self._provider = provider
        init_kw: dict[str, Any] = {"api_key": key}
        base_url = _resolve_base_url(provider)
        if base_url:
            init_kw["base_url"] = base_url
        self._client: OpenAI = OpenAI(**init_kw)

    @property
    def provider(self) -> VLMProvider:
        return self._provider

    def describe(
        self,
        image_bytes: bytes,
        *,
        prompt: str,
        mime: str = "image/png",
    ) -> str:
        """Send a single image + text prompt; return the model's reply text."""
        url = _data_url(image_bytes, mime)
        kwargs: dict[str, Any] = {
            "model": self._provider.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": url}},
                    ],
                },
            ],
        }
        if self._provider.max_tokens is not None:
            kwargs["max_tokens"] = self._provider.max_tokens
        if self._provider.temperature is not None:
            kwargs["temperature"] = self._provider.temperature

        def _call() -> str:
            resp = self._client.chat.completions.create(**kwargs)
            if not resp.choices:
                return ""
            message = resp.choices[0].message
            content = getattr(message, "content", "") or ""
            return str(content)

        return retry_with_backoff(
            _call,
            retryable=_VLM_RETRYABLE,
            max_attempts=self._provider.retry_max_attempts,
            base_seconds=self._provider.retry_base_seconds,
        )

    def describe_path(self, path: Path, *, prompt: str) -> str:
        """Load an image from disk and call :meth:`describe`."""
        data = Path(path).read_bytes()
        return self.describe(data, prompt=prompt, mime=_infer_mime(Path(path)))
