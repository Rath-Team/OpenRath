# 工具

工具解析位于 [后端与沙箱](backends.md)（执行）与 [Workflow 与 AgentParam](workflow_agent.md)（编排）之间：全局 `ToolTable` 决定模型发出的工具名对应哪一个 `FlowToolCall` 或进程内函数。

## FlowToolCall 体系

`rath.flow.tool` 中的 ``flow_tool_*`` 辅助函数接收已绑定沙箱的 :class:`~rath.session.session.Session`，构造对应的不可变 ``BackendTool`` 载荷并调用 ``Session.require_sandbox().dispatch``，返回后端结果类型（如 :class:`~rath.backend.results.CommandResult`、:class:`~rath.backend.results.FileContent` 等）。

| 辅助函数 | 典型用途 |
|----------|----------|
| `flow_tool_command_run(session, cmd, …)` | 在沙箱内执行 Shell/命令 |
| `flow_tool_files_read` / `flow_tool_files_write` | 文件读写 |
| `flow_tool_files_list` / `flow_tool_files_exists` | 目录探测 |
| `flow_tool_code_run` | 在支持时由解释器执行代码 |

这与**会话沙箱**上的快捷调用一致：先 ``Session.to("local", …)`` 等绑定后端，再传入 ``session`` 与路径或命令参数即可。

## 全局 ToolTable

`global_tool_table()` 是 `run_session_loop` 使用的**唯一**注册表。默认沙箱循环工具（`run_shell_command`、`write_workspace_file`）在**首次**访问全局表时安装（包括 `import rath.flow.tool` 时）。

`extend_builtin_sandbox_tools(table)` 可把上述默认重新应用到任意 `ToolTable`（隔离测试时常用）。

## 进程内工具 `@tool`

`tool(...)`（类 LangChain）用 Pydantic `args_schema` 注册 **Python** 可调用对象。模型选中该工具时，入参经 Pydantic 校验，函数在 `run_session_loop` 内**进程内**执行（不经沙箱）。若必须在 `BackendSandbox` 上执行，请用沙箱侧的 `ToolRegistration` 构造器。

名称冲突时 `register_global_tool` 抛出 `ToolNameConflictError`。

## ToolRegistration

条目分两类：

1. **沙箱** — `builder(args) -> FlowToolCall`，显式 JSON Schema `parameters`。
2. **进程内** — `inline_fn` + `args_schema`（`type[pydantic.BaseModel]`）；给 LLM 的 schema 通常来自 `args_schema.model_json_schema()`。

对两类均可使用 `ToolTable.resolve(name, arguments)`；`ToolTable.build` **仅**接受沙箱工具。

## 分发路径

在 `run_session_loop` 中：

1. 工具定义来自 `global_tool_table()`；执行器的 `tool_schemas()` 可覆盖对外展示的列表。
2. assistant 消息可携带 tool 调用。
3. 每次调用经表 **解析**；**沙箱** 解析走 `executor.dispatch_tool` → `BackendSandbox.dispatch`；**进程内** 解析调用已注册的 Python 函数，并将返回值 JSON 序列化后给模型。

不支持的沙箱载荷会在后端层以 `UnsupportedBackendTool` 抛出。

---

**下一篇：** [工作流](workflow_agent.md)
