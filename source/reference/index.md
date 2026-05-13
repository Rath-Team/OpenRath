# API Reference
This section organizes the public API by the actual package structure. Each page contains three kinds of information:

| Information | Purpose |
| --- | --- |
| Source | Corresponding source files for jumping back to the implementation. |
| Public contract | Common signatures, parameters, return values, and exceptions. |
| Autodoc | Class/function documentation imported from the current source. |

## Package structure
| Package | Contents |
| --- | --- |
| [`rath`](rath.md) | Package-level entrypoint. |
| [`rath.session`](session.md) | `Session`, chunks, loop, compression, lineage, registry. |
| [`rath.backend`](backend.md) | Backend abstractions, sandboxes, tool payloads, results, registry, stream. |
| [`rath.flow`](flow.md) | `Workflow`, `AgentParam`, `Agent`, `Compressor`. |
| [`rath.flow.tool`](flow_tool.md) | `FlowToolCall`, built-in system tools, backend tool factories, schema merging. |
| [`rath.llm`](llm.md) | `Provider`, request/response types, OpenAI-compatible client. |
| [`rath.utils`](utils.md) | `.env` and project-root helpers. |

```{toctree}
---
maxdepth: 2
caption: API Reference
---

rath
session
backend
flow
flow_tool
llm
utils
```
