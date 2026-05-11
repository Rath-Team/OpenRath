# LLM
OpenRath 默认使用 OpenAI-compatible chat client。高级集成可以替换 `SessionLoopExecutor`，接管模型调用、响应解析和工具派发。

本页说明 OpenRath 构造 OpenAI-compatible request、规范化 response、替换 client 或 executor 的位置。

## 源码地图
| 文件 | 负责内容 |
| --- | --- |
| `src/rath/llm/provider.py` | `Provider` request options。 |
| `src/rath/llm/client.py` | `RathOpenAIChatClient`。 |
| `src/rath/llm/settings.py` | `.env` 与环境变量加载。 |
| `src/rath/llm/chat_request.py` | request dataclasses。 |
| `src/rath/llm/chat_response.py` | normalized response dataclasses。 |
| `src/rath/llm/openai_create_kwargs.py` | internal request 到 OpenAI SDK kwargs 的转换。 |
| `src/rath/llm/openai_normalize.py` | OpenAI completion 到 internal response 的转换。 |
| `src/rath/session/provider_builtin.py` | 默认 `SessionLoopExecutor`。 |

## Provider 参数
`Provider` 是请求参数对象。它保存模型名、采样参数、tool choice、response format 和透传参数。

```python
from rath.llm import Provider

provider = Provider(
    model="gpt-5.5",
    temperature=0.2,
    parallel_tool_calls=False,
)
```

`provider_into_chat_request(...)` 会把 `Provider` 合并到 `RathLLMChatRequest`。messages 和 tools 由 session loop 构造。

## 默认客户端
`RathOpenAIChatClient` 包装 `openai.OpenAI().chat.completions.create(...)`。

| 环境变量 | 用途 |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI 或兼容网关 API key。 |
| `OPENAI_BASE_URL` | OpenAI-compatible endpoint。 |
| `OPENAI_DEFAULT_MODEL` | `Provider.model` 为空时使用的默认模型。 |

当前默认 client 是同步、non-streaming chat completion 路径。`to_create_kwargs(...)` 会强制 `stream=False`。

## SessionLoopExecutor 执行器
`SessionLoopExecutor` 是 loop 的替换点。

```python
class SessionLoopExecutor(Protocol):
    def complete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
        ...

    def dispatch_tool(self, session, tool, arguments):
        ...

    def tool_schemas(self):
        ...
```

| 方法 | 作用 |
| --- | --- |
| `complete(req)` | 执行一次 chat completion。 |
| `dispatch_tool(session, tool, arguments)` | 执行 `FlowToolCall`。 |
| `tool_schemas()` | 返回 tool schema；空 tuple 时 loop 使用本地工具表生成 schema。 |

`DefaultSessionLoopExecutor` 使用 `RathOpenAIChatClient` 完成模型请求，并直接调用 `tool(session, arguments)` 执行工具。

## 请求与响应
OpenRath 内部使用标准化 dataclass：

| 类型 | 作用 |
| --- | --- |
| `RathLLMChatRequest` | messages、tools、model、sampling 参数和 extra args。 |
| `RathLLMChatResponse` | normalized non-streaming completion。 |
| `RathLLMMessage` | system/user/assistant/tool message。 |
| `RathLLMFunctionTool` | OpenAI-style function tool schema。 |

## 集成点
| 需求 | 扩展点 |
| --- | --- |
| 更换 OpenAI-compatible 网关 | 设置 `OPENAI_BASE_URL`。 |
| 更换模型和采样参数 | 设置 `Provider(...)` 或 `OPENAI_DEFAULT_MODEL`。 |
| 使用本地模型服务 | 实现 `SessionLoopExecutor.complete(...)`。 |
| 自定义工具派发策略 | 实现 `SessionLoopExecutor.dispatch_tool(...)`。 |
| 测试固定模型响应 | 使用 scripted executor。 |

## 调用路径
默认 session loop 的 LLM 调用路径：

```text
run_session_loop
  -> provider_into_chat_request(messages, tools, Provider, default_tool_choice="auto")
  -> DefaultSessionLoopExecutor.complete(req)
  -> RathOpenAIChatClient.complete(req)
  -> to_create_kwargs(req, default_model=settings.default_model)
  -> openai.OpenAI(...).chat.completions.create(**kwargs)
  -> normalize_chat_completion(completion)
```

compress 路径使用同一套 client 和 request/response DTO，但传入 `tools=None` 和 `default_tool_choice="none"`。

## 边界条件
| 行为 | 当前实现 |
| --- | --- |
| missing API key | `load_rath_llm_settings(...)` 抛 `ValueError`。 |
| missing model | `to_create_kwargs(...)` 在 `req.model` 与 default model 都为空时抛 `ValueError`。 |
| streaming | `extra_create_args["stream"] is True` 时抛 `ValueError`，最终 kwargs 设置 `stream=False`。 |
| tool argument parsing | `normalize_chat_completion(...)` 尝试 JSON parse arguments，并记录 parse error flag。 |
| empty choices | `RathLLMChatResponse.primary_choice` 抛 `IndexError`。 |

## 测试覆盖
| 行为 | 测试 |
| --- | --- |
| request/response wire shape | `tests/session/test_llm_message_wire.py` |
| live OpenAI-compatible client | `tests/llm/test_openai_chat_real.py` |
| scripted loop executor | `tests/session/scripted_loop_executor.py` |
| integration loop/compress | `tests/integration/test_session_loop_real.py`, `tests/integration/test_session_compress_real.py` |
