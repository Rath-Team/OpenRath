(pkg-flow-tool)=
# `rath.flow.tool`

Model-visible tool interface, built-in tools, tool table merging, and backend payload factories.

## Source
| Module | Source |
| --- | --- |
| `rath.flow.tool.base` | `src/rath/flow/tool/base.py` |
| `rath.flow.tool.system_tool` | `src/rath/flow/tool/system_tool.py` |
| `rath.flow.tool.tool_table` | `src/rath/flow/tool/tool_table.py` |

## Public contract
### `FlowToolCall`

| Member | Type | Description |
| --- | --- | --- |
| `name` | `str` | OpenAI function tool name. |
| `description` | `str` \| `None` | Optional tool description. |
| `parameters` | `Mapping[str, Any]` | JSON Schema object. |
| `__call__(session, arguments)` | `Any` | Runtime execution entrypoint. |

### Built-in tools
| Tool | Name | Arguments | Behavior |
| --- | --- | --- | --- |
| `RunShellCommandTool` | `run_shell_command` | `{cmd: string}` | Calls `BackendToolCommandRun`. |
| `WriteWorkspaceFileTool` | `write_workspace_file` | `{path: string, content: string}` | Calls `BackendToolFilesWrite`. |

`RunShellCommandTool` rejects multiline commands and commands longer than 2048 characters. `WriteWorkspaceFileTool` requires `content` to be text.

### Tool table
| Function | Returns | Behavior |
| --- | --- | --- |
| `global_system_tools()` | `dict[str, FlowToolCall]` | Returns the in-process singleton built-in tool table. |
| `merge_tools_for_loop(user_tools)` | `dict[str, FlowToolCall]` | Merges built-in tools and user tools. |
| `tools_dict_to_schemas(table)` | `tuple[RathLLMFunctionTool, ...]` | Converts to OpenAI-style function tool schemas. |

When a user tool name conflicts with a built-in tool name, `merge_tools_for_loop(...)` raises `ToolNameConflictError`.

### Backend tool factories
| Function | Returns |
| --- | --- |
| `flow_tool_command_run(cmd, env=None, cwd=None, stdin=None, timeout=None)` | `BackendToolCommandRun` |
| `flow_tool_files_read(path, encoding="utf-8")` | `BackendToolFilesRead` |
| `flow_tool_files_write(path, data, mode=0o644)` | `BackendToolFilesWrite` |
| `flow_tool_files_list(path)` | `BackendToolFilesList` |
| `flow_tool_files_exists(path)` | `BackendToolFilesExists` |
| `flow_tool_code_run(code, language="python", timeout=None)` | `BackendToolCodeRun` |

## Autodoc
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

[← API Reference](index.md)
