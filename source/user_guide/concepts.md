# 设计概览

OpenRath 的核心判断是：Agent 工作流的状态不应该只存在于一段 prompt 字符串里，而应该成为一个可传递、可派生、可绑定执行环境的对象。这个对象就是 `Session`。

## PyTorch 类比

OpenRath 借用 PyTorch 的表达方式，但并不包装 PyTorch。

| PyTorch 中的直觉 | OpenRath 中的对应 | 真实代码 |
| --- | --- | --- |
| Tensor 承载数据 | Session 承载对话分块和 sandbox placement | `rath.session.Session` |
| Module 组织参数和 forward | Workflow 组织 `AgentParam` 并实现 `forward` | `rath.flow.Workflow` |
| device 决定执行位置 | Backend 决定工具在哪种 sandbox 中执行 | `rath.backend.Backend` |
| functional API 构造操作 | `flow_tool_*` 工厂构造后端工具载荷 | `rath.flow.tool.flow_tool_command_run` 等 |

边界也很重要：OpenRath 没有 tensor、autograd、optimizer，也不做模型训练框架。它处理的是 LLM agent 的状态、工具和执行环境。

## 真实运行路径

`run_session_loop` 每一轮都会把 `agent_session.chunk_table` 放在用户侧历史之前，然后请求聊天补全。若模型返回工具调用，循环会找到同名 `FlowToolCall`，执行后把结果作为 `tool_result` chunk 追加回会话。若模型不再请求工具，循环追加最终 assistant chunk 并返回新的 `Session`。

## 设计原则

1. `Session` 是一等对象：工作流输入输出都是 `Session`，而不是裸字符串。
2. 执行环境显式绑定：工具必须通过 `BackendSandbox` 执行，或者作为用户自定义 `FlowToolCall` 在 Python 进程内执行。
3. LLM 客户端可替换：`SessionLoopExecutor` 是协议，默认实现只是同步 OpenAI-compatible 调用。
4. 工具 schema 和工具执行绑定在一起：一个 `FlowToolCall` 同时提供 `name`、`description`、`parameters` 和 `__call__`。
5. 谱系只做轻量记录：`parent_session_ids` 等字段用于调试和追踪，不是数据库或持久化系统。

**下一篇：** [主要组件](main_components.md)
