# LLM 请求接口

OpenRath 的 LLM 层是薄封装：内部类型跟 OpenAI chat completions 线协议接近，默认客户端调用 `openai.OpenAI`。

## Provider

`Provider` 是冻结 dataclass，用来保存除 `messages` / `tools` 外的 OpenAI-style 参数。

常用字段：

| 字段 | 含义 |
| --- | --- |
| `model` | 模型名；为 `None` 时使用 `OPENAI_DEFAULT_MODEL`。 |
| `temperature` / `top_p` | 采样参数。 |
| `max_tokens` / `max_completion_tokens` | 输出长度限制。 |
| `tool_choice` | 工具选择策略；未设置时 loop 默认 `"auto"`，压缩默认 `"none"`。 |
| `parallel_tool_calls` | 是否允许并行工具调用，透传给 provider。 |
| `response_format` | JSON mode 等响应格式配置。 |
| `reasoning_effort` / `verbosity` | 兼容支持这些字段的 provider。 |
| `extra_create_args` | 透传额外参数。 |

示例：

```python
from rath.flow import Provider

provider = Provider(
    model="gpt-5.5",
    temperature=0.2,
    max_tokens=1000,
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

## 默认客户端

`RathOpenAIChatClient` 需要传入已配置好的 `Provider`（至少含非空 `api_key` ）。应用可自行从环境变量组装 `Provider`；`OPENAI_BASE_URL` / `OPENAI_DEFAULT_MODEL` 等与 `Provider` 字段对应。

环境变量（常见做法，非客户端自动加载）：

| 变量 | 必需 | 作用 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 是 | 填入 `Provider(api_key=...)`。 |
| `OPENAI_BASE_URL` | 否 | 非空时填入 `Provider.base_url`。 |
| `OPENAI_DEFAULT_MODEL` | 否 | 填入 `Provider.model`。 |

若 `api_key` 为空，`RathOpenAIChatClient` 构造会抛 `ValueError`。

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

**下一篇：** [示例](../examples/index.md)
