(pkg-flow-tool)=
# `rath.flow.tool`

Model-visible tool interface, built-in tools, tool table merging, and backend payload factories.

## Source
| Module | Source |
| --- | --- |
| `rath.flow.tool.base` | `src/rath/flow/tool/base.py` |
| `rath.flow.tool.system_tool` | `src/rath/flow/tool/system_tool.py` |
| `rath.flow.tool.tool_table` | `src/rath/flow/tool/tool_table.py` |
| `rath.flow.tool.mcp_adapter` | `src/rath/flow/tool/mcp_adapter.py` |

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

### MCP stdio adapter
```{figure} ../_static/mcp-tool-adapter.png
:alt: MCP stdio tool adapter

The MCP adapter discovers stdio server tools and exposes each one as a normal
`FlowToolCall` for the OpenRath session loop.
```

| API | Returns | Behavior |
| --- | --- | --- |
| `MCPClient(command, args=None, env=None)` | client | Synchronous wrapper around a stdio MCP server. |
| `MCPClient.list_tools()` | list | Opens a subprocess, initializes MCP, and returns raw tool definitions. |
| `MCPClient.call_tool(name, arguments)` | raw result | Opens a subprocess and calls one MCP tool. |
| `MCPToolCall` | `FlowToolCall` | Wraps one MCP tool as a model-visible OpenRath tool. |
| `mcp_tools_from_server(command, args=None, env=None)` | tuple | Discovers all tools from a stdio server. |
| `mcp_tools_from_config(name=None)` | tuple | Reads one MCP server entry from `~/.openrath/config.json`. |

The adapter currently supports stdio transport only. Each list/call opens a fresh subprocess on a shared dedicated event loop, so tool lifecycle is simple and there is no explicit close step.

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

MCP adapter APIs are documented manually above because importing the third-party
`mcp` package during a docs build can depend on the installed Pydantic minor
version. Runtime users should import them from `rath.flow.tool.mcp_adapter`.

[← API Reference](index.md)
