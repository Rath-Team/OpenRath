# LLM 请求接口

OpenRath 的 LLM 层是薄封装：内部类型接近 chat completions 线协议，默认通过 provider registry 选择具体客户端。内置客户端目前包括 OpenAI-compatible 和 Anthropic。

## Provider

`Provider` 是冻结 dataclass，用来保存除 `messages` / `tools` 外的模型路由和采样参数。

常用字段：

| 字段 | 含义 |
| --- | --- |
| `provider_kind` | `None` / `"openai"` 使用 OpenAI-compatible 客户端；`"anthropic"` 使用 Anthropic 客户端。 |
| `model` | 模型名。未显式传入时，客户端会按环境变量和 config fallback 解析。 |
| `base_url` / `api_key` | provider 连接信息。显式字段优先级最高。 |
| `temperature` / `top_p` | 采样参数。 |
| `max_tokens` / `max_completion_tokens` | 输出长度限制。 |
| `tool_choice` | 工具选择策略；未设置时 loop 默认 `"auto"`，压缩默认 `"none"`。 |
| `parallel_tool_calls` | 是否允许并行工具调用，透传给 provider。 |
| `response_format` | JSON mode 等响应格式配置。 |
| `reasoning_effort` / `verbosity` | 兼容支持这些字段的 provider。 |
| `extra_create_args` | 透传额外参数。 |
| `retry_max_attempts` / `retry_base_seconds` | transient API error 的重试策略。 |
| `budget_total_tokens` / `on_budget_exceeded` | session 累计 token 超预算时的 guard。 |

示例：

```python
from rath.flow import Provider

provider = Provider(
    model="gpt-5.5",
    temperature=0.2,
    max_tokens=1000,
)
```

如果项目已经写入 `~/.openrath/config.json`，可以直接从配置构造：

```python
provider = Provider.from_config("openai-main", temperature=0.2)
```

Anthropic 使用同一个 `Provider`：

```python
provider = Provider(
    provider_kind="anthropic",
    model="claude-sonnet-4-5",
    api_key="sk-ant-...",
)
```

## 请求类型

`RathLLMMessage` 表示 `messages[]` 中的一项，支持 `system`、`user`、`assistant`、`tool`、`developer` 等角色字符串。

`RathLLMFunctionTool` 表示 function-style tool schema：

```python
RathLLMFunctionTool(
    name="run_shell_command",
    description="Run one shell command inside the active sandbox workspace.",
    parameters={...},
)
```

`RathLLMChatRequest` 汇总 messages、tools、tool_choice 和 Provider 参数。

## 客户端选择

`run_session_loop(...)` 不直接写死具体 provider，而是通过：

```python
from rath.llm import chat_client_for

client = chat_client_for(provider)
```

registry 默认映射：

| `provider_kind` | 客户端 |
| --- | --- |
| `None` / `"openai"` | `RathOpenAIChatClient` |
| `"anthropic"` | `RathAnthropicChatClient` |

可以用 `register_chat_client(kind, factory)` 注册自定义 provider。

## 配置和环境变量

OpenAI-compatible 客户端的常见 fallback：

| 变量 | 必需 | 作用 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 否 | 未显式传 `api_key` 时使用。 |
| `OPENAI_BASE_URL` | 否 | 未显式传 `base_url` 时使用。 |
| `OPENAI_DEFAULT_MODEL` | 否 | 未显式传 `model` 时使用。 |
| `AZURE_OPENAI_ENDPOINT` | 否 | Azure OpenAI endpoint fallback。 |
| `AZURE_OPENAI_API_KEY` / `AZURE_API_KEY` | 否 | Azure key fallback。 |
| `OPENAI_API_VERSION` / `AZURE_OPENAI_API_VERSION` | 否 | Azure API version fallback。 |

Anthropic 客户端使用：

| 变量 | 作用 |
| --- | --- |
| `ANTHROPIC_API_KEY` | Anthropic key fallback。 |
| `ANTHROPIC_DEFAULT_MODEL` | Anthropic model fallback。 |

如果字段、环境变量都没有命中，客户端会再查 `config.json` 中同 kind 的 provider。

OpenRath 不再自动加载 `.env`。如果仍想使用 `.env`，在启动进程前由 shell、部署平台或应用自行加载。

## Streaming

OpenAI-compatible streaming 通过同一个 session loop 暴露：

```python
def on_event(delta):
    if delta.content:
        print(delta.content, end="", flush=True)

out = run_session_loop(
    user_session=user_session,
    agent_session=agent_session,
    agent_provider=provider,
    on_event=on_event,
)
```

`on_event` 要求解析出的客户端满足 `StreamingChatClient`。当前 OpenAI-compatible 客户端支持；Anthropic 客户端是非 streaming，传 `on_event` 会在 session 注册前抛 `TypeError`。

## 预算 guard

```python
from rath.llm import BudgetExceededError, Provider

def stop_on_budget(**info):
    raise BudgetExceededError(str(info))

provider = Provider(
    model="gpt-5.5",
    budget_total_tokens=20_000,
    on_budget_exceeded=stop_on_budget,
)
```

guard 基于 `Session.cumulative_usage`。同一个 loop 第一次越过阈值时触发一次；如果 callback 抛异常，loop 会中止。

## 响应归一化

`RathLLMChatResponse` 封装 provider 返回：

- `primary_choice`：当前 loop 使用的首选 choice；
- `message.content`：普通 assistant 文本；
- `message.tool_calls`：工具调用列表；
- `usage`：如 provider 返回 token usage，则保留。

工具 arguments 会尝试 JSON parse。parse 失败时，`arguments_parsed=None` 且 `arguments_parse_error=True`，随后 session loop 会把错误作为 tool result 反馈给模型。

## 替换客户端

不要直接改 `run_session_loop`。实现 `SessionLoopExecutor` 协议即可替换：

```python
class MyExecutor:
    def complete(self, req):
        return my_gateway(req)

    def dispatch_tool(self, session, tool, arguments):
        return tool(session, arguments)

    def tool_schemas(self):
        return ()
```

测试中也使用这一方式构造 scripted executor，避免真实 LLM 请求。

**下一篇：** [示例](../tutorial/examples/index.md)
