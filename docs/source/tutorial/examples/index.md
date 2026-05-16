# Runnable Examples

These pages map to the `example/` scripts and subdirectories in the repository. After the core tutorials, use them to see how sessions, tools, sandboxes, and workflows fit together in runnable scripts.

## Basic Usage
Start here if you want the smallest runnable scripts before moving into backends or integrations.

| Page | Script | Covers |
| --- | --- | --- |
| [Session Usage](session_usage.md) | `example/session_usage.py` | The path from session creation to loop and compression. |
| [Custom Tool Usage](custom_tool_usage.md) | `example/custom_tool_usage.py` | Wrapping an external service as a `FlowToolCall`. |

## Runtime & Backends
Use these when you need to understand where tool side effects happen.

| Page | Script | Covers |
| --- | --- | --- |
| [Local Backend](sandbox_backend_local.md) | `example/sandbox_backend_local.py` | Temporary directories and project directory binding with the local backend. |
| [OpenSandbox Backend](sandbox_backend_opensandbox.md) | `example/sandbox_backend_opensandbox.py` | OpenSandbox backend, workspace binding, and service health checks. |

## LLM & Integrations
Use these when the question is about model providers, streaming, MCP tools, or runtime inspection.

| Page | Script | Covers |
| --- | --- | --- |
| [Streaming Chat](streaming_chat.md) | `example/streaming_chat.py` | `run_session_loop(on_event=...)`, stream deltas, and token usage. |
| [Anthropic Provider](anthropic_provider.md) | `example/anthropic_provider.py` | `Provider(provider_kind="anthropic")`. |
| [MCP Tool Usage](mcp_tool_usage.md) | `example/mcp_tool_usage.py` | Wrapping stdio MCP tools as `FlowToolCall`. |
| [Lineage Export](lineage_export.md) | `example/lineage_export.py` | Exporting session lineage as JSONL. |

## Workflow Examples
Use these when you want to study larger agent programs and composition patterns.

| Page | Script | Covers |
| --- | --- | --- |
| [Trading Agents](trading_agents.md) | `example/trading_agents/` | Multi-role workflow, external data tools, and session-level parallel branches. |
| [Engineering Agents](engineering_agents.md) | `example/engineering_agents/` | Nested workflows, engineering task decomposition, and parallelizable subtasks. |
| [Research Transformer](research_transformer.md) | `example/research_transformer/` on `main` | Academic writing pipeline with branch workflows, per-role providers, compression, and an optional image tool. |

## Before running
All examples that call a real LLM need an OpenAI-compatible gateway. The docs do not store real keys; manage API keys through shell environment variables, CI secrets, or your deployment secret store:

```bash
export OPENAI_API_KEY=...
export OPENAI_BASE_URL=...
export OPENAI_DEFAULT_MODEL=...
```

Examples that use external services list their extra variables on the relevant page. For example, Trading Agents requires `ALPHA_VANTAGE_API_KEY`, and the OpenSandbox example requires an available OpenSandbox server.

## What to inspect
| Target | Why it matters |
| --- | --- |
| stdout | Shows the final assistant message or output session. |
| workspace | Confirms whether tools actually wrote files. |
| chunk table | Shows the order of user, assistant, and tool result rows. |
| workflow repr | Confirms which `AgentParam` instances were registered directly. |
| environment variables | Confirms whether the model gateway, external APIs, and OpenSandbox service are active. |

```{toctree}
---
maxdepth: 2
caption: Runnable Examples
---

session_usage
custom_tool_usage
sandbox_backend_local
sandbox_backend_opensandbox
streaming_chat
anthropic_provider
mcp_tool_usage
lineage_export
trading_agents
engineering_agents
research_transformer
```
