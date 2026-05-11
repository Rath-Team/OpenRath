# LLM 请求接口

[Workflow 与 AgentParam](workflow_agent.md) 在 `run_session_loop` 中贯穿 `Provider`。本章说明该数据类本身，以及在未注入自定义执行器时循环如何构造默认的 OpenAI 兼容客户端。

## Provider

`rath.llm.Provider` 是冻结数据类，描述除演化的 `messages` / `tools` 载荷外的**全部**内容——亦即 `run_session_loop` 合并进 `RathLLMChatRequest` 的 kwargs。

典型字段：

| 字段 | 含义 |
|------|------|
| `model` | 提供方特定的聊天模型 ID |
| `temperature`、`top_p`、`max_tokens` 等 | 与 OpenAI SDK 类似的采样参数 |
| `tool_choice`、`parallel_tool_calls` | 工具调用策略提示 |

可混用 `flow.Provider(...)` 与 `rath.llm.Provider(...)`（`flow.AgentParam` 引用同一类型）。

## RathOpenAIChatClient

`RathOpenAIChatClient` 包装**同步**的 OpenAI 兼容 HTTP 调用（实现内部遵循 openai-python 用法）。

构造时读取：

- 环境变量（`OPENAI_API_KEY`、`OPENAI_BASE_URL` 等）；
- 可选的 `.env`（`python-dotenv`）。

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
