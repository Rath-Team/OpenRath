# LLM 请求接口

[Workflow 与 AgentParam](workflow_agent.md) 在 `run_session_loop` 中贯穿 `Provider`。本章说明该数据类本身，以及在未注入自定义执行器时循环如何从 `Provider` 构造默认的 OpenAI 兼容客户端。

## Provider

`rath.llm.Provider` 是冻结数据类，描述除演化的 `messages` / `tools` 载荷外的**全部**内容——亦即 `run_session_loop` 合并进 `RathLLMChatRequest` 的 kwargs，外加默认 HTTP 客户端所需字段。

典型字段：

| 字段 | 含义 |
|------|------|
| `base_url` | OpenAI 兼容网关基址（可选） |
| `api_key` | API 密钥；在使用默认执行器且未自定义 `executor` 时必填 |
| `model`、 `temperature`、`top_p`、`max_tokens` 等 | 模型 ID 与 OpenAI SDK 风格采样参数 |
| `tool_choice`、`parallel_tool_calls` | 工具调用策略提示 |

可混用 `flow.Provider(...)` 与 `rath.llm.Provider(...)`（`flow.AgentParam` 引用同一类型）。

框架不在库内提供「从环境自动构造 `Provider`」的 API。请在应用里用 `os.environ`（或你的配置系统）读取 `OPENAI_API_KEY`（必填）、`OPENAI_BASE_URL`、`OPENAI_DEFAULT_MODEL`，再实例化 `Provider`；仓库内 `example/_openai_provider.py` 可作为示例拷贝。

## RathOpenAIChatClient

`RathOpenAIChatClient(provider)` 包装**同步**的 OpenAI 兼容 HTTP 调用（实现内部遵循 openai-python 用法）。`provider.api_key` 必填；`provider.base_url` 非空时传入 SDK。

当前 Rath **未**在框架层强制 HTTP 超时——若策略需要硬时限，请在外层包裹调用。

## 请求与响应

`rath.llm.chat_request` / `chat_response` 存放为循环规范化提供方载荷的数据类（`RathLLMChatRequest`、`RathLLMChatResponse`、消息/工具结构）。

类型有意跟踪 OpenAI 线协议，以便更换网关时改动面集中。

## 接入点

`DefaultSessionLoopExecutor` 将 `RathOpenAIChatClient` 适配到 `SessionLoopExecutor` 协议：

- `complete(req)` 发起聊天补全；
- `dispatch_tool(session, call)` 将 Flow 调用转发到 `session` 所附沙箱；
- `tool_schemas()` 暴露模型侧期望的注册信息。

需要追踪、缓存、批处理或换厂商时，替换 `executor=` 即可，而保持 `run_session_loop` 不变。

---

**下一篇：** [示例](../examples/index.md)
