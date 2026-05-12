(pkg-llm)=
# `rath.llm`

OpenAI-compatible 请求/响应类型、同步客户端与 response normalization。

## 源码（Source）

| 模块 | 源码 |
| --- | --- |
| `rath.llm.provider` | `src/rath/llm/provider.py` |
| `rath.llm.client` | `src/rath/llm/client.py` |
| `rath.llm.chat_request` | `src/rath/llm/chat_request.py` |
| `rath.llm.chat_response` | `src/rath/llm/chat_response.py` |
| `rath.llm.openai_create_kwargs` | `src/rath/llm/openai_create_kwargs.py` |
| `rath.llm.openai_normalize` | `src/rath/llm/openai_normalize.py` |

## 公共契约（Public Contract）

### `Provider`

`Provider` 保存 loop 需要的 model、sampling、tool 和 provider-specific 参数。它不包含 messages 和 tools；这两项由 session loop 构造。

可显式构造，或从环境变量自行读取后填入 `api_key` / `base_url` / `model`（本库不再提供统一的 settings 加载函数）。

| 字段类别 | 字段 |
| --- | --- |
| model | `model` |
| sampling | `temperature`, `top_p`, `max_completion_tokens`, `max_tokens`, `stop`, `n`, `seed` |
| penalties | `frequency_penalty`, `presence_penalty`, `logit_bias` |
| tools/output | `tool_choice`, `parallel_tool_calls`, `response_format` |
| OpenAI options | `reasoning_effort`, `verbosity`, `metadata`, `user`, `store`, `service_tier`, `extra_create_args` |

### 客户端（Client）

```python
from rath.llm import Provider, RathOpenAIChatClient

client = RathOpenAIChatClient(Provider(api_key="sk-..."))
response = client.complete(request)
```

`RathOpenAIChatClient` 构造时必须传入含非空 `api_key` 的 `Provider` 。`complete(...)` 调用 `openai.OpenAI(...).chat.completions.create(...)`，并把 provider 返回值 normalize 成 `RathLLMChatResponse`。

### 请求与响应 DTO（Request/Response DTO）

| 类型 | 说明 |
| --- | --- |
| `RathLLMMessage` | chat `messages[]` 元素。 |
| `RathLLMFunctionTool` | function-style tool schema。 |
| `RathLLMChatRequest` | OpenAI-compatible request kwargs。 |
| `RathLLMChatResponse` | normalized non-streaming response。 |
| `RathLLMChatChoice` | 单个 choice。 |
| `RathLLMAssistantMessage` | assistant message，包括 tool calls。 |
| `RathLLMToolCallPart` / `RathLLMToolCallFunction` | tool call 结构。 |
| `RathLLMTokenUsage` | usage 统计。 |

### 创建参数（Create Kwargs）

`to_create_kwargs(req, default_model=...)` 会把内部 request 转成 OpenAI SDK kwargs。

| 行为 | 说明 |
| --- | --- |
| model selection | 使用 `req.model`，否则使用 `default_model`；都为空时抛 `ValueError`。 |
| tool schema | `RathLLMFunctionTool` 转成 `{"type": "function", "function": ...}`。 |
| stream | `stream=True` 会抛 `ValueError`，最终 kwargs 强制 `stream=False`。 |
| extra args | `req.extra_create_args` 最后 merge。 |

## 自动文档（Autodoc）

```{eval-rst}
.. autoclass:: rath.llm.Provider
   :members:

.. autoclass:: rath.llm.RathOpenAIChatClient
   :members:

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

[← API 参考](index.md)
