(pkg-llm)=
# `rath.llm`

OpenAI-compatible request/response types, synchronous client, configuration loading, and response normalization.

## Source
| Module | Source |
| --- | --- |
| `rath.llm.provider` | `src/rath/llm/provider.py` |
| `rath.llm.client` | `src/rath/llm/client.py` |
| `rath.llm.settings` | `src/rath/llm/settings.py` |
| `rath.llm.chat_request` | `src/rath/llm/chat_request.py` |
| `rath.llm.chat_response` | `src/rath/llm/chat_response.py` |
| `rath.llm.openai_create_kwargs` | `src/rath/llm/openai_create_kwargs.py` |
| `rath.llm.openai_normalize` | `src/rath/llm/openai_normalize.py` |

## Public contract
### `Provider`

`Provider` stores the model, sampling, tool, and provider-specific parameters required by the loop. It does not contain messages or tools; the session loop constructs those.

| Field category | Fields |
| --- | --- |
| model | `model` |
| sampling | `temperature`, `top_p`, `max_completion_tokens`, `max_tokens`, `stop`, `n`, `seed` |
| penalties | `frequency_penalty`, `presence_penalty`, `logit_bias` |
| tools/output | `tool_choice`, `parallel_tool_calls`, `response_format` |
| OpenAI options | `reasoning_effort`, `verbosity`, `metadata`, `user`, `store`, `service_tier`, `extra_create_args` |

### Settings
| Function/type | Behavior |
| --- | --- |
| `RathLLMSettings` | `api_key`, `base_url`, `default_model`. |
| `load_rath_llm_settings(dotenv_path=None)` | Loads `.env`, then reads environment variables. |
| `rath_llm_default_dotenv_path()` | Returns `.env` under the project root. |

When `OPENAI_API_KEY` is empty, `load_rath_llm_settings(...)` raises `ValueError`.

### Client
```python
client = RathOpenAIChatClient()
response = client.complete(request)
```

`RathOpenAIChatClient.complete(...)` calls `openai.OpenAI().chat.completions.create(...)` and normalizes the provider response to `RathLLMChatResponse`.

### Request and response DTOs
| Type | Description |
| --- | --- |
| `RathLLMMessage` | Chat `messages[]` element. |
| `RathLLMFunctionTool` | Function-style tool schema. |
| `RathLLMChatRequest` | OpenAI-compatible request kwargs. |
| `RathLLMChatResponse` | Normalized non-streaming response. |
| `RathLLMChatChoice` | Single choice. |
| `RathLLMAssistantMessage` | Assistant message, including tool calls. |
| `RathLLMToolCallPart` / `RathLLMToolCallFunction` | Tool call structure. |
| `RathLLMTokenUsage` | Usage statistics. |

### Create arguments
`to_create_kwargs(req, default_model=...)` converts the internal request to OpenAI SDK kwargs.

| Behavior | Description |
| --- | --- |
| model selection | Uses `req.model`; otherwise uses `default_model`. Raises `ValueError` if both are empty. |
| tool schema | Converts `RathLLMFunctionTool` to `{"type": "function", "function": ...}`. |
| stream | `stream=True` raises `ValueError`; final kwargs force `stream=False`. |
| extra args | Merges `req.extra_create_args` last. |

## Autodoc
```{eval-rst}
.. autoclass:: rath.llm.Provider
   :members:

.. autoclass:: rath.llm.RathOpenAIChatClient
   :members:

.. autoclass:: rath.llm.RathLLMSettings
   :members:

.. autofunction:: rath.llm.load_rath_llm_settings

.. autofunction:: rath.llm.to_create_kwargs

.. autofunction:: rath.llm.normalize_chat_completion

.. autoclass:: rath.llm.RathLLMChatRequest
   :members:

.. autoclass:: rath.llm.RathLLMMessage
   :members:

.. autoclass:: rath.llm.RathLLMFunctionTool
   :members:

.. autoclass:: rath.llm.RathLLMChatResponse
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
```

[← API Reference](index.md)
