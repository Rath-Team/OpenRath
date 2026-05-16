# Tutorials
Tutorials are the entry point for learning OpenRath. They are organized in the order you are likely to use the project: build a `Session`, understand where tools run, then move into the agent loop and multi-agent Workflow.

Each tutorial focuses on code snippets, key-line notes, and observed behavior. Together they cover the common path from basic API usage to Workflow customization.

## Core Learning Path
| Order | Page | What it covers |
| --- | --- | --- |
| 1 | [Session Basics](session_basics.md) | Create user and agent sessions, and understand `fork()`, `detach()`, and Backend placement. |
| 2 | [Local Sandbox Tools](local_sandbox_tools.md) | Open a local Backend directly and see how file, command, and code payloads run around a workspace. |
| 3 | [Session Loop Tool Calls](session_loop_tools.md) | Understand model tool calls, tool dispatch, `tool_result` chunks, and the next completion round. |
| 4 | [Custom FlowToolCall](custom_flow_tool.md) | Define your own tool schema and Python execution logic, then pass it into the Session loop. |
| 5 | [Runnable Examples](examples/index.md) | Move from focused tutorials into runnable scripts grouped by usage, runtime, integrations, and workflows. |

## Example Groups
| Group | Use it for | Entry |
| --- | --- | --- |
| Basic Usage | See the smallest runnable paths through sessions and custom tools. | [Session Usage](examples/session_usage.md), [Custom Tool Usage](examples/custom_tool_usage.md) |
| Runtime & Backends | Check where tools execute and how sandbox backends behave. | [Local Backend](examples/sandbox_backend_local.md), [OpenSandbox Backend](examples/sandbox_backend_opensandbox.md) |
| LLM & Integrations | Try streaming, Anthropic routing, MCP tools, and lineage inspection. | [Streaming Chat](examples/streaming_chat.md), [Anthropic Provider](examples/anthropic_provider.md), [MCP Tool Usage](examples/mcp_tool_usage.md), [Lineage Export](examples/lineage_export.md) |
| Workflow Examples | Study larger multi-role and multi-stage agent programs. | [Trading Agents](examples/trading_agents.md), [Engineering Agents](examples/engineering_agents.md), [Research Transformer](examples/research_transformer.md) |

## Choose by Task
| Task | Start with |
| --- | --- |
| Understand OpenRath's state model | [Session Basics](session_basics.md) |
| Check which directory tools run in | [Local Sandbox Tools](local_sandbox_tools.md) |
| See how an agent calls tools across turns | [Session Loop Tool Calls](session_loop_tools.md) |
| Wrap an external API as a model-callable tool | [Custom FlowToolCall](custom_flow_tool.md) |
| Connect OpenSandbox | [OpenSandbox backend](examples/sandbox_backend_opensandbox.md) |
| Try a streaming UI callback | [Streaming Chat](examples/streaming_chat.md) |
| Use an Anthropic model | [Anthropic Provider](examples/anthropic_provider.md) |
| Wrap an MCP server as tools | [MCP Tool Usage](examples/mcp_tool_usage.md) |
| Inspect session lineage | [Lineage Export](examples/lineage_export.md) |
| Build a multi-role agent flow | [Trading Agents](examples/trading_agents.md) and [Engineering Agents](examples/engineering_agents.md) |

## How to Read
Each page uses the same structure:

1. Read the coverage table first to confirm what the page explains.
2. Follow the code steps to understand the API boundary.
3. Compare the key-line notes to see where state changes.
4. Run or rewrite the exercises to turn the example into your own code.
5. If behavior is unexpected, check the troubleshooting table first, then use Developer Notes for source-level details.

```{toctree}
---
maxdepth: 2
caption: Tutorials
---

session_basics
local_sandbox_tools
session_loop_tools
custom_flow_tool
examples/index
```
