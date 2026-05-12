(pkg-flow-tool)=
# `rath.flow.tool`

结构化工具调用、`ToolTable`、全局注册与 `@tool` 装饰器。用户指南：[工具与 ToolTable](../user_guide/tools.md)。

* `FlowToolCall`（及与 `BackendTool` 的别名关系）、各 ``flow_tool_*`` 会话辅助函数（在 ``Session`` 上 ``dispatch``）。
* `ToolTable.resolve` / `build`、`global_tool_table`、`extend_builtin_sandbox_tools`。
* 基于 Pydantic `args_schema` 的 `tool()`、进程内工具与沙箱工具注册；首次触摸全局表时安装内置沙箱工具。

---

[← API 参考](index.md)
