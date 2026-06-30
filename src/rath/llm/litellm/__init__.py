"""LiteLLM adapter for :class:`rath.llm.ChatClient`.

Imports of this subpackage auto-register
:class:`~rath.llm.litellm.client.RathLiteLLMChatClient` under
``provider_kind="litellm"``.
"""

from __future__ import annotations

from rath.llm.litellm.client import LITELLM_RETRYABLE, RathLiteLLMChatClient
from rath.llm.registry import register_chat_client

register_chat_client("litellm", RathLiteLLMChatClient)

__all__ = [
    "RathLiteLLMChatClient",
    "LITELLM_RETRYABLE",
]
