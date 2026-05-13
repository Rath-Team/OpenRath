# Tutorials
Tutorials are the entry point for learning OpenRath. They are organized in the order you are likely to use the project: build a `Session`, understand where tools run, then move into the agent loop and multi-agent Workflow.

Each tutorial focuses on code snippets, key-line notes, and observed behavior. Together they cover the common path from basic API usage to Workflow customization.

## Learning Path
| Order | Page | What it covers |
| --- | --- | --- |
| 1 | [Session Basics](session_basics.md) | Create user and agent sessions, and understand `fork()`, `detach()`, and Backend placement. |
| 2 | [Local Sandbox Tools](local_sandbox_tools.md) | Open a local Backend directly and see how file, command, and code payloads run around a workspace. |
| 3 | [Session Loop Tool Calls](session_loop_tools.md) | Understand model tool calls, tool dispatch, `tool_result` chunks, and the next completion round. |
| 4 | [Custom FlowToolCall](custom_flow_tool.md) | Define your own tool schema and Python execution logic, then pass it into the Session loop. |
| 5 | [Runnable Examples](examples/index.md) | Learn real Workflow, OpenSandbox, and multi-agent patterns from repository scripts. |

## Choose by Task
| Task | Start with |
| --- | --- |
| Understand OpenRath's state model | [Session Basics](session_basics.md) |
| Check which directory tools run in | [Local Sandbox Tools](local_sandbox_tools.md) |
| See how an agent calls tools across turns | [Session Loop Tool Calls](session_loop_tools.md) |
| Wrap an external API as a model-callable tool | [Custom FlowToolCall](custom_flow_tool.md) |
| Build a multi-role agent flow | [Trading Agents](examples/trading_agents.md) and [Engineering Agents](examples/engineering_agents.md) |
| Connect OpenSandbox | [OpenSandbox backend](examples/sandbox_backend_opensandbox.md) |

## How to Read
Each page uses the same structure:

1. Read the coverage table first to confirm what the page explains.
2. Follow the code steps to understand the API boundary.
3. Compare the key-line notes to see where state changes.
4. Run or rewrite the exercises to turn the example into your own code.
5. If behavior is unexpected, check the troubleshooting table first, then use Developer Notes for source-level details.

## Runnable Examples
These pages map to scripts and subdirectories under `example/`:

| Page | Script | Focus |
| --- | --- | --- |
| [Session Usage Example](examples/session_usage.md) | `example/session_usage.py` | The continuous path through `Session`, `run_session_loop`, and `run_session_compress`. |
| [Custom Tool Example](examples/custom_tool_usage.md) | `example/custom_tool_usage.py` | Wrap an external service as a `FlowToolCall`. |
| [Local Backend Example](examples/sandbox_backend_local.md) | `example/sandbox_backend_local.py` | Bind `Session.to("local", spec=...)` to a local directory. |
| [OpenSandbox Backend Example](examples/sandbox_backend_opensandbox.md) | `example/sandbox_backend_opensandbox.py` | Bind `Session.to("opensandbox", spec=...)` to a container workspace. |
| [Trading Agents](examples/trading_agents.md) | `example/trading_agents/` | Sequential multi-role research Workflow. |
| [Engineering Agents](examples/engineering_agents.md) | `example/engineering_agents/` | Nested Workflow. |

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
