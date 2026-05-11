(pkg-flow-tool)=
# `rath.flow.tool`

模型可见工具接口、内置工具、工具表合并和 backend payload factory。

## 源码（Source）

| 模块 | 源码 |
| --- | --- |
| `rath.flow.tool.base` | `src/rath/flow/tool/base.py` |
| `rath.flow.tool.system_tool` | `src/rath/flow/tool/system_tool.py` |
| `rath.flow.tool.tool_table` | `src/rath/flow/tool/tool_table.py` |

## 公共契约（Public Contract）

### `FlowToolCall`

| 成员 | 类型 | 说明 |
| --- | --- | --- |
| `name` | `str` | OpenAI function tool name。 |
| `description` | `str` \| `None` | 可选工具说明。 |
| `parameters` | `Mapping[str, Any]` | JSON Schema object。 |
| `__call__(session, arguments)` | `Any` | runtime 执行入口。 |

### 内置工具（Built-in Tools）

| Tool | Name | 参数 | 行为 |
| --- | --- | --- | --- |
| `RunShellCommandTool` | `run_shell_command` | `{cmd: string}` | 调用 `BackendToolCommandRun`。 |
| `WriteWorkspaceFileTool` | `write_workspace_file` | `{path: string, content: string}` | 调用 `BackendToolFilesWrite`。 |

`RunShellCommandTool` 会拒绝多行命令和超过 2048 字符的命令。`WriteWorkspaceFileTool` 要求 `content` 是 text。

### 工具表（Tool Table）

| 函数 | 返回 | 行为 |
| --- | --- | --- |
| `global_system_tools()` | `dict[str, FlowToolCall]` | 返回进程内 singleton 内置工具表。 |
| `merge_tools_for_loop(user_tools)` | `dict[str, FlowToolCall]` | 合并内置工具与用户工具。 |
| `tools_dict_to_schemas(table)` | `tuple[RathLLMFunctionTool, ...]` | 转为 OpenAI-style function tool schema。 |

用户工具名与内置工具名冲突时，`merge_tools_for_loop(...)` 抛 `ToolNameConflictError`。

### 后端工具工厂（Backend Tool Factories）

| 函数 | 返回 |
| --- | --- |
| `flow_tool_command_run(cmd, env=None, cwd=None, stdin=None, timeout=None)` | `BackendToolCommandRun` |
| `flow_tool_files_read(path, encoding="utf-8")` | `BackendToolFilesRead` |
| `flow_tool_files_write(path, data, mode=0o644)` | `BackendToolFilesWrite` |
| `flow_tool_files_list(path)` | `BackendToolFilesList` |
| `flow_tool_files_exists(path)` | `BackendToolFilesExists` |
| `flow_tool_code_run(code, language="python", timeout=None)` | `BackendToolCodeRun` |

## 自动文档（Autodoc）

```{eval-rst}
.. autoclass:: rath.flow.tool.FlowToolCall
   :members:

.. autoclass:: rath.flow.tool.RunShellCommandTool
   :members:

.. autoclass:: rath.flow.tool.WriteWorkspaceFileTool
   :members:

.. autofunction:: rath.flow.tool.global_system_tools

.. autofunction:: rath.flow.tool.merge_tools_for_loop

.. autofunction:: rath.flow.tool.tools_dict_to_schemas

.. autofunction:: rath.flow.tool.flow_tool_command_run

.. autofunction:: rath.flow.tool.flow_tool_files_read

.. autofunction:: rath.flow.tool.flow_tool_files_write

.. autofunction:: rath.flow.tool.flow_tool_files_list

.. autofunction:: rath.flow.tool.flow_tool_files_exists

.. autofunction:: rath.flow.tool.flow_tool_code_run

.. autoexception:: rath.flow.tool.ToolNameConflictError
```

[← API 参考](index.md)
