# 工作流

[工具与 ToolTable](tools.md) 把模型可见的名字接到实现上。**Workflow** 装载 [`AgentParam`](workflow_agent.md) 并实现 `forward`；下面的 `run_session_loop` 则是交替补全与工具轮次的同步内核。读完本章后请看 [LLM 客户端与配置](llm.md)，了解 `Provider` 与 `RathOpenAIChatClient` 如何接入。

## Workflow

`Workflow` 子类组织多智能体编排：

1. 将 `AgentParam` 赋给属性以实例化各智能体参数（如 `self.planner`）。
2. 实现 `forward(self, session: Session) -> Session`（阻塞）。

调用 `workflow(session)` 会委托给 `forward`。`named_agents()` 按名排序枚举已注册的 `(name, agent)`，用法接近 `nn.Module.named_children()`。

`repr(workflow)` 会缩进嵌套的 `AgentParam`/`Session` 预览，类似嵌套模块。

### 调用 `run_session_loop`

从 `rath.session` 使用 `run_session_loop`：传入用户 `Session`、`agent_session` 与来自 `AgentParam` 的 `agent_provider`（可选 `executor`、`tools`、`max_tool_rounds`、`chunk_print`）。

## AgentParam

`AgentParam` 打包：

| 字段 | 用途 |
|------|------|
| `agent_session` | 在 `run_session_loop` 内拼在用户分块**之前**的指令型 `Session`。 |
| `provider` | 携带模型、采样与端点信息的 `Provider`（`model`、`temperature`、`api_key`、`base_url`、`tool_choice` 等）。 |

`AgentParam.data` 提供两字段的只读映射视图，便于调试。

`AgentParam` **不**拥有传输层（`complete`）或沙箱分发——这些在 `SessionLoopExecutor` 内。

## 会话循环内核

`run_session_loop(user_session, agent_session, *, agent_provider, executor=None, max_tool_rounds=16, chunk_print=None)` **同步**运行：

- 将 `chunk_table_to_messages(agent_session)` 与演化的用户会话行拼接为消息。
- 通过 `executor.complete(RathLLMChatRequest(...))` 请求补全。
- 经 `global_tool_table().resolve(...)` 解析每个工具调用：**沙箱** 工具走 `executor.dispatch_tool(session_snapshot, FlowToolCall)`；**进程内** `@tool` 在进程内执行并将结果序列化给模型。
- 追加 assistant 分块与序列化后的工具反馈，直到无工具或达到轮次上限。

传入 ``chunk_print``（推荐使用 :func:`~rath.session.sink_chunk_print` 包一层
``print`` 或其它单参数写入函数，对**每个新追加的** assistant / tool-result 分块调用
``hook(row, index, out)``）时，只在对应分块写入 ``out.chunk_table`` 之后调用一次，
便于逐行观察，而不会每次打印整张表。

``run_session_compress(..., chunk_print=...)`` 在压缩结果会话建好、沙箱重绑之后，
对**唯一**产出的 user 分块调用 ``hook(row, 0, out)`` 一次。

若省略 `executor`，OpenRath 会构造 `DefaultSessionLoopExecutor(RathOpenAIChatClient(agent_provider))`；此时 `agent_provider.api_key` 必须非空（或传入自定义执行器）。

### 可运行示例

- [`example/session_usage.py`](https://github.com/Rath-Team/OpenRath/blob/main/example/session_usage.py) — 端到端 `run_session_loop`、本地沙箱与 Provider。
- [`tests/flow/test_workflow_agent.py`](https://github.com/Rath-Team/OpenRath/blob/main/tests/flow/test_workflow_agent.py) — 最小 `Workflow` 子类与 `named_agents()`。

---

**下一篇：** [LLM 请求接口](llm.md)
