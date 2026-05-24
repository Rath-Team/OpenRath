"""OpenAI- and Anthropic-compatible LLM access (synchronous chat completions).

Public surface:

* Request / response dataclasses (`RathLLM*`) and the `Provider` config object.
* `ChatClient` / `StreamingChatClient` Protocols for adapter implementations.
* `RathOpenAIChatClient` and `RathAnthropicChatClient` built-in adapters.
* `chat_client_for(provider)` + `register_chat_client(kind, factory)` for
  registry-based dispatch — the single point of routing that replaces the
  old ``provider.provider_kind == "anthropic"`` string checks.
* `to_create_kwargs` / `normalize_chat_completion` (OpenAI) and
  `build_anthropic_kwargs` / `normalize_anthropic_response` (Anthropic) are
  re-exported for tests and advanced callers building their own loops.
"""

# Import adapter subpackages for their registration side-effects. Order matters:
# registry must be defined before adapters call register_chat_client. The
# concrete client classes are re-exported here so users can ``from rath.llm
# import RathOpenAIChatClient`` regardless of the underlying layout.
from rath.llm.anthropic import (
    RathAnthropicChatClient,
    build_anthropic_kwargs,
    normalize_anthropic_response,
)
from rath.llm.base import ChatClient, StreamingChatClient
from rath.llm.budget import BudgetExceededError
from rath.llm.chat_request import (
    RathLLMChatRequest,
    RathLLMFunctionTool,
    RathLLMMessage,
    RathLLMRole,
)
from rath.llm.chat_response import (
    RathLLMAssistantMessage,
    RathLLMChatChoice,
    RathLLMChatResponse,
    RathLLMFinishReason,
    RathLLMStreamDelta,
    RathLLMTokenUsage,
    RathLLMToolCallFunction,
    RathLLMToolCallPart,
    add_usage,
)
from rath.llm.embedding import (
    DEFAULT_EMBEDDING_MODEL,
    EmbeddingProvider,
    RathOpenAIEmbeddingClient,
)
from rath.llm.openai import (
    RathOpenAIChatClient,
    normalize_chat_completion,
    to_create_kwargs,
)
from rath.llm.provider import Provider
from rath.llm.registry import (
    ChatClientFactory,
    chat_client_for,
    register_chat_client,
    registered_kinds,
)
from rath.llm.vlm import RathOpenAIVLMClient, VLMProvider

__all__ = [
    # Protocols & registry
    "ChatClient",
    "StreamingChatClient",
    "ChatClientFactory",
    "chat_client_for",
    "register_chat_client",
    "registered_kinds",
    # Built-in adapters
    "RathOpenAIChatClient",
    "RathAnthropicChatClient",
    # Embedding adapter (sync, OpenAI-compatible)
    "EmbeddingProvider",
    "RathOpenAIEmbeddingClient",
    "DEFAULT_EMBEDDING_MODEL",
    # VLM adapter (sync, OpenAI-compatible vision)
    "VLMProvider",
    "RathOpenAIVLMClient",
    # Config + errors
    "Provider",
    "BudgetExceededError",
    # Pure helpers (OpenAI)
    "to_create_kwargs",
    "normalize_chat_completion",
    # Pure helpers (Anthropic)
    "build_anthropic_kwargs",
    "normalize_anthropic_response",
    # Token accounting
    "add_usage",
    # Request types
    "RathLLMChatRequest",
    "RathLLMMessage",
    "RathLLMFunctionTool",
    "RathLLMRole",
    # Response types
    "RathLLMChatResponse",
    "RathLLMChatChoice",
    "RathLLMAssistantMessage",
    "RathLLMFinishReason",
    "RathLLMStreamDelta",
    "RathLLMTokenUsage",
    "RathLLMToolCallPart",
    "RathLLMToolCallFunction",
]
