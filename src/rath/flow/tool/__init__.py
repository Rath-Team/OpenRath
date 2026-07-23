"""Tool registration, :class:`~rath.flow.tool.base.FlowToolCall`, and session-scoped helpers."""

from __future__ import annotations

from rath.flow.tool.base import FlowToolCall
from rath.flow.tool.dispatch import (
    ToolDispatchResult,
    dispatch_flow_tool,
    project_tool_result,
    serialize_tool_result,
)
from rath.flow.tool.mcp_adapter import (
    MCPClient,
    MCPToolCall,
    mcp_tools_from_config,
    mcp_tools_from_server,
    shared_mcp_loop,
)
from rath.flow.tool.policy import ToolPolicy, ToolPolicyEnforcer
from rath.flow.tool.system_tool import (
    FlowToolCodeRun,
    FlowToolCommandRun,
    FlowToolFilesExists,
    FlowToolFilesList,
    FlowToolFilesRead,
    FlowToolFilesWrite,
    flow_tool_code_run,
    flow_tool_command_run,
    flow_tool_files_exists,
    flow_tool_files_list,
    flow_tool_files_read,
    flow_tool_files_write,
    global_system_tools,
)
from rath.flow.tool.tool_table import (
    ToolNameConflictError,
    merge_tools_for_loop,
    tools_dict_to_schemas,
)

# Register built-in :class:`FlowToolCall` handlers for the session loop.
global_system_tools()

__all__ = [
    "FlowToolCall",
    "FlowToolCodeRun",
    "FlowToolCommandRun",
    "FlowToolFilesExists",
    "FlowToolFilesList",
    "FlowToolFilesRead",
    "FlowToolFilesWrite",
    "MCPClient",
    "MCPToolCall",
    "ToolNameConflictError",
    "ToolDispatchResult",
    "ToolPolicy",
    "ToolPolicyEnforcer",
    "dispatch_flow_tool",
    "flow_tool_code_run",
    "flow_tool_command_run",
    "flow_tool_files_exists",
    "flow_tool_files_list",
    "flow_tool_files_read",
    "flow_tool_files_write",
    "global_system_tools",
    "merge_tools_for_loop",
    "mcp_tools_from_config",
    "mcp_tools_from_server",
    "shared_mcp_loop",
    "project_tool_result",
    "serialize_tool_result",
    "tools_dict_to_schemas",
]
