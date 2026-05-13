# Developer Notes
Developer Notes explain OpenRath's core components and runtime boundaries. They are written for developers who want to extend OpenRath, read the source, write custom workflows, or connect a new backend.

This page maps the main component pages to the relevant source files and tests.

## Component map
| Component | Covers | Entry point |
| --- | --- | --- |
| `Session` | Context table, backend placement, session graph. | [Session](session.md) |
| `Sandbox` | Backend registration, sandbox lifecycle, local/OpenSandbox behavior. | [Sandbox](sandbox.md) |
| `Tool` | `FlowToolCall`, backend payloads, tool result chunks, streams. | [Tool](tool.md) |
| `AgentParam` | Agent-side system session and provider options. | [Agent Param](agent_param.md) |
| `Workflow` | Composable agent workflow modules. | [Workflow](workflow.md) |
| `LLM` | Request construction, OpenAI-compatible client, executor replacement points. | [LLM](llm.md) |

## Reading order
| Goal | Suggested order |
| --- | --- |
| Understand the runtime path | `Session` -> `Sandbox` -> `Tool` |
| Write a single agent | `AgentParam` -> `Workflow` -> `LLM` |
| Write a multi-agent workflow | `Workflow` -> `AgentParam` -> `Session` |
| Write a custom tool | `Tool` -> `Sandbox` -> `Session` |
| Connect a new model gateway | `LLM` -> `AgentParam` |

## Source and tests
| Component | Main source | Main tests |
| --- | --- | --- |
| `Session` | `src/rath/session/session.py`, `loop.py`, `compress.py`, `graph/` | `tests/session/`, `tests/integration/test_session_*_real.py` |
| `Sandbox` | `src/rath/backend/abc.py`, `local.py`, `opensandbox.py` | `tests/backends/`, `tests/conformance/`, `tests/unit/test_registry.py` |
| `Tool` | `src/rath/flow/tool/`, `src/rath/backend/tool_types.py` | `tests/session/test_tool_registry.py`, `tests/flow/test_flow_tool_user_subclass.py`, `tests/unit/test_flow_tool.py` |
| `AgentParam` | `src/rath/flow/agent_param.py`, `src/rath/flow/agent.py` | `tests/flow/test_workflow_agent.py`, `tests/test_import.py` |
| `Workflow` | `src/rath/flow/workflow.py`, `agent.py`, `compressor.py` | `tests/flow/test_workflow_agent.py` |
| `LLM` | `src/rath/llm/`, `src/rath/session/provider_builtin.py` | `tests/llm/`, `tests/session/test_llm_message_wire.py` |

Developer Notes describe behavior that exists in the current source. Roadmap notes, troubleshooting, and full application tutorials are tracked separately.

```{toctree}
---
maxdepth: 2
caption: Developer Notes
---

session
sandbox
tool
agent_param
workflow
llm
```
