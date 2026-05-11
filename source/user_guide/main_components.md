# 主要组件

下面这张图是当前源码的真实分层。读代码时可以按这条线索定位责任边界。

## `rath.session`

`Session` 是运行时状态容器。它持有：

- `chunk_table`：按顺序保存 `system`、`user`、`assistant`、`tool_result` 等 chunk；
- sandbox 绑定：`sandbox`、`sandbox_backend`、`_sandbox_open_spec`；
- lineage 字段：`parent_session_ids`、`lineage_operator`、`lineage_kind`、`lineage_extras`。

`run_session_loop` 是同步的 agent 循环；`run_session_compress` 是一次性 LLM 压缩调用。

## `rath.backend`

`Backend` 定义沙箱运行时接口。当前公共注册名包括：

- `local`：主机进程/文件系统沙箱，始终可用；
- `opensandbox`：可选依赖存在且环境配置可用时注册可用。

后端消费的是 `BackendTool*` 数据类，返回 `ToolResult` 子类或 `bool`。

## `rath.flow.tool`

`FlowToolCall` 是 session loop 的模型可见工具抽象，层级高于 `BackendTool`：

- `FlowToolCall.name` 进入 LLM tool schema；
- `FlowToolCall.parameters` 是 JSON Schema；
- `FlowToolCall.__call__(session, arguments)` 执行工具逻辑；
- 内置 `RunShellCommandTool` 和 `WriteWorkspaceFileTool` 会进一步构造后端工具载荷并调用 `session.require_sandbox().dispatch(...)`。

## `rath.flow`

`Workflow` 通过属性赋值收集 `AgentParam`，类似 `nn.Module` 收集子模块。`AgentParam` 只包含 `agent_session` 和 `Provider`，不持有 HTTP client 或 sandbox executor。

`Agent` 是一个薄封装：给定 system prompt、model 和工具列表，调用时进入 `run_session_loop`。

## `rath.llm`

`Provider` 存放 OpenAI-style 采样和路由参数。`RathOpenAIChatClient` 是同步 OpenAI-compatible client，负责把内部请求类型转成 `chat.completions.create(...)` 参数，再把 SDK 响应归一化成 `RathLLMChatResponse`。

**下一篇：** [会话](session.md)
