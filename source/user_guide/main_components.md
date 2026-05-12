# OpenRath 主要组件

下文对应 PyTorch 中**数据、模块、函数式算子、设备后端**的分工，并适配 LLM 智能体与沙箱工具。请按此顺序阅读；每节链向详解章节。

## 会话

[`Session`](session.md) 存放 [`ChunkTable`](session.md) 及可选的沙箱绑定。可用 `Session.from_user_message`、`Session.from_agent_prompt` 等构造叶会话，用 `.to(backend_name, spec=...)` 挂载后端，再传入 `Workflow.forward` / `run_session_loop`。

## 沙箱后端

[`BackendSandbox`](backends.md) 是会话打开沙箱时获得的**运行时句柄**。[`Backend.dispatch`](backends.md) 执行工具载荷（`FlowToolCall` / `BackendTool`）并返回类型化结果（`CommandResult`、`FileContent` 等）。本地与 OpenSandbox 适配器位于 `rath.backend.local` 与 `rath.backend.opensandbox`（可选 extra）。

## 工具

[`ToolTable`](tools.md) 将 OpenAI 风格的工具名映射到 **沙箱** 构建器（`FlowToolCall`）或经 Pydantic 校验的 **进程内** `@tool` 可调用对象。全进程单例 [`global_tool_table()`](tools.md) 为 `run_session_loop` 所依赖。

## 工作流

[`Workflow`](workflow_agent.md) 的子类实现 `forward(session) -> session`。将 [`AgentParam`](workflow_agent.md) 赋给属性，以便 `named_agents()` 枚举——类似 `nn.Module` 注册子模块。

## Agent 参数

[`AgentParam`](workflow_agent.md) 包含：

- `agent_session` — 在循环中拼在用户分块**之前**的 system / 开发者侧 `Session` 分块；
- `provider` — 并入每次补全请求的 [`Provider`](llm.md) 字段。

`AgentParam` 刻意不包含 HTTP 客户端或执行器；后者属于会话循环执行器。

## 会话循环

[`run_session_loop`](workflow_agent.md) 在 **聊天补全** 与 **工具轮次** 间交替：把 `agent_session` 的分块与用户会话的演变合并、经全局工具表解析、通过执行器分发沙箱调用，并返回带 assistant 与 tool 结果行的新 `Session`。

## LLM 请求接口

[`RathOpenAIChatClient`](llm.md) 由 [`Provider`](llm.md) 构造并执行同步聊天补全。[`DefaultSessionLoopExecutor`](workflow_agent.md) 包装该客户端，实现 `SessionLoopExecutor`，并把对外声明的工具 schema 桥接到沙箱分发。

**下一篇：** [会话](session.md)
