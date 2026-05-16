(pkg-llm)=
# `rath.llm`

Provider options, request/response types, OpenAI and Anthropic clients, streaming deltas, retry, budget accounting, and response normalization.

## Source
| Module | Source |
| --- | --- |
| `rath.llm.provider` | `src/rath/llm/provider.py` |
| `rath.llm.base` | `src/rath/llm/base.py` |
| `rath.llm.registry` | `src/rath/llm/registry.py` |
| `rath.llm.openai.client` | `src/rath/llm/openai/client.py` |
| `rath.llm.anthropic.client` | `src/rath/llm/anthropic/client.py` |
| `rath.llm.chat_request` | `src/rath/llm/chat_request.py` |
| `rath.llm.chat_response` | `src/rath/llm/chat_response.py` |
| `rath.llm.openai.create_kwargs` | `src/rath/llm/openai/create_kwargs.py` |
| `rath.llm.openai.normalize` | `src/rath/llm/openai/normalize.py` |
| `rath.llm.anthropic.create_kwargs` | `src/rath/llm/anthropic/create_kwargs.py` |
| `rath.llm.anthropic.normalize` | `src/rath/llm/anthropic/normalize.py` |

## Public contract
### `Provider`

`Provider` stores OpenAI-compatible client identity plus model, sampling, tool, and provider-specific parameters required by the loop. It does not contain messages or tools; the session loop constructs those.

| Field category | Fields |
| --- | --- |
| client identity | `api_key`, `base_url`, `provider_kind` |
| model | `model` |
| sampling | `temperature`, `top_p`, `max_completion_tokens`, `max_tokens`, `stop`, `n`, `seed` |
| penalties | `frequency_penalty`, `presence_penalty`, `logit_bias` |
| tools/output | `tool_choice`, `parallel_tool_calls`, `response_format` |
| OpenAI options | `reasoning_effort`, `verbosity`, `metadata`, `user`, `store`, `service_tier`, `extra_create_args` |
| retry/budget | `retry_max_attempts`, `retry_base_seconds`, `budget_total_tokens`, `on_budget_exceeded` |

`Provider.from_config(name=None, **overrides)` builds a provider from `~/.openrath/config.json`; explicit overrides win over the file.

### Client
```python
from rath.llm import Provider, RathOpenAIChatClient, chat_client_for

provider = Provider(api_key="sk-...", base_url=None, model="gpt-5.5")
client = RathOpenAIChatClient(provider)
response = client.complete(request)

anthropic = Provider(provider_kind="anthropic", model="claude-sonnet-4-5")
client = chat_client_for(anthropic)
```

`chat_client_for(provider)` dispatches through the registry. Built-in kinds are OpenAI-compatible (`None` or `"openai"`) and Anthropic (`"anthropic"`). Third-party adapters can call `register_chat_client(kind, factory)`.

```{figure} ../_static/provider-dispatch-registry.png
:alt: Provider dispatch registry

`Provider.provider_kind` selects a registered chat-client factory; new provider
kinds integrate at the registry boundary instead of changing the session loop.
```

### Request and response DTOs
| Type | Description |
| --- | --- |
| `RathLLMMessage` | Chat `messages[]` element. |
| `RathLLMFunctionTool` | Function-style tool schema. |
| `RathLLMChatRequest` | OpenAI-compatible request kwargs. |
| `RathLLMChatResponse` | Normalized completion response. |
| `RathLLMStreamDelta` | Normalized streaming delta. |
| `RathLLMChatChoice` | Single choice. |
| `RathLLMAssistantMessage` | Assistant message, including tool calls. |
| `RathLLMToolCallPart` / `RathLLMToolCallFunction` | Tool call structure. |
| `RathLLMTokenUsage` | Usage statistics. |

### Create arguments
`to_create_kwargs(req, default_model=...)` converts the internal request to non-streaming OpenAI SDK kwargs. `RathOpenAIChatClient.complete_stream(...)` uses the streaming sibling and yields `RathLLMStreamDelta` chunks.

```{figure} ../_static/streaming-loop-deltas.png
:alt: Streaming loop deltas

Streaming forwards deltas to `on_event` while the session loop still appends one
durable assistant chunk per completed model round.
```

| Behavior | Description |
| --- | --- |
| model selection | Uses `req.model`; otherwise uses `default_model`. Raises `ValueError` if both are empty. |
| tool schema | Converts `RathLLMFunctionTool` to `{"type": "function", "function": ...}`. |
| stream | Non-streaming kwargs force `stream=False`; streaming kwargs force `stream=True`. |
| extra args | Merges `req.extra_create_args` last. |

### Environment and config fallback
| Client | Resolution order |
| --- | --- |
| OpenAI API key | `Provider.api_key` → Azure-aware env vars → matching config provider. |
| OpenAI base URL | `Provider.base_url` → `OPENAI_BASE_URL` → `AZURE_OPENAI_ENDPOINT` → config. |
| OpenAI model | `Provider.model` → `OPENAI_DEFAULT_MODEL` → config default provider model. |
| Anthropic API key | `Provider.api_key` → `ANTHROPIC_API_KEY` → matching config provider. |
| Anthropic base URL | `Provider.base_url` → `ANTHROPIC_BASE_URL` → config. |
| Anthropic model | `Provider.model` → `ANTHROPIC_DEFAULT_MODEL` → config provider model. |

Legacy Azure endpoints are routed through `openai.AzureOpenAI`; `/openai/v1` endpoints use the standard OpenAI client.

```{figure} ../_static/llm-resilience-budget.png
:alt: LLM retry, usage, and budget guard flow

Retries, usage aggregation, and budget checks sit around provider calls without
changing the public `Session` and `Provider` API shape.
```

## Autodoc
```{eval-rst}
.. autoclass:: rath.llm.Provider
   :members:

.. autoclass:: rath.llm.RathOpenAIChatClient
   :members:

.. autoclass:: rath.llm.RathAnthropicChatClient
   :members:

.. autoclass:: rath.llm.ChatClient
   :members:

.. autoclass:: rath.llm.StreamingChatClient
   :members:

.. autofunction:: rath.llm.chat_client_for

.. autofunction:: rath.llm.register_chat_client

.. autofunction:: rath.llm.registered_kinds

.. autofunction:: rath.llm.to_create_kwargs

.. autofunction:: rath.llm.normalize_chat_completion

.. autofunction:: rath.llm.build_anthropic_kwargs

.. autofunction:: rath.llm.normalize_anthropic_response

.. autoclass:: rath.llm.RathLLMChatRequest
   :members:

.. autoclass:: rath.llm.RathLLMMessage
   :members:

.. autoclass:: rath.llm.RathLLMFunctionTool
   :members:

.. autoclass:: rath.llm.RathLLMChatResponse
   :members:

.. autoclass:: rath.llm.RathLLMStreamDelta
   :members:

.. autoclass:: rath.llm.RathLLMChatChoice
   :members:

.. autoclass:: rath.llm.RathLLMAssistantMessage
   :members:

.. autoclass:: rath.llm.RathLLMToolCallPart
   :members:

.. autoclass:: rath.llm.RathLLMToolCallFunction
   :members:

.. autoclass:: rath.llm.RathLLMTokenUsage
   :members:

.. autofunction:: rath.llm.add_usage

.. autoexception:: rath.llm.BudgetExceededError
```

[← API Reference](index.md)
