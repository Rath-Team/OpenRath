# MCP Tool Usage

This page maps to `example/mcp_tool_usage.py`.

## What it covers
| Step | API |
| --- | --- |
| Launch a stdio MCP server | `mcp_tools_from_server([...])`. |
| Wrap server tools | `MCPToolCall` implements `FlowToolCall`. |
| Use config later | `mcp_tools_from_config(name)`. |

Run:

```bash
python example/mcp_tool_usage.py
```

The example uses `example/_demo_echo_server.py`, so no external MCP server is required. For a real deployment, replace the command:

```python
tools = mcp_tools_from_server(["python", "-m", "mcp_server_filesystem"])
```

Or define the command in `~/.openrath/config.json`:

```json
{
  "mcp": {
    "default_enabled": ["filesystem"],
    "servers": {
      "filesystem": {
        "command": ["python", "-m", "mcp_server_filesystem"],
        "env": {}
      }
    }
  }
}
```

The adapter supports stdio transport. It opens a fresh subprocess for each tool listing and each tool call.

