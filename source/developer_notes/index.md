# Developer Notes
Developer Notes 解释 OpenRath 的核心组件和运行边界。这里面向想要扩展 OpenRath、读源码、写自定义 workflow 或接入新 backend 的开发者。

本页整理核心组件入口，以及组件、源码、测试之间的对应关系。

## 组件地图
| 组件 | 负责内容 | 入口 |
| --- | --- | --- |
| `Session` | 上下文表、backend placement、session graph。 | [Session](session.md) |
| `Sandbox` | backend 注册、sandbox 生命周期、local/OpenSandbox 行为。 | [Sandbox](sandbox.md) |
| `Tool` | `FlowToolCall`、backend payload、tool result chunk、stream。 | [Tool](tool.md) |
| `AgentParam` | agent-side system session 和 provider 参数。 | [Agent Param](agent_param.md) |
| `Workflow` | 可组合的 agent workflow 模块。 | [Workflow](workflow.md) |
| `LLM` | request 构造、OpenAI-compatible client、executor 替换点。 | [LLM](llm.md) |

## 阅读顺序
| 目标 | 阅读顺序 |
| --- | --- |
| 理解运行路径 | `Session` → `Sandbox` → `Tool` |
| 写单 agent | `AgentParam` → `Workflow` → `LLM` |
| 写 multi-agent workflow | `Workflow` → `AgentParam` → `Session` |
| 写自定义工具 | `Tool` → `Sandbox` → `Session` |
| 接新模型网关 | `LLM` → `AgentParam` |

## 源码与测试
| 组件 | 主要源码 | 主要测试 |
| --- | --- | --- |
| `Session` | `src/rath/session/session.py`, `loop.py`, `compress.py`, `graph/` | `tests/session/`, `tests/integration/test_session_*_real.py` |
| `Sandbox` | `src/rath/backend/abc.py`, `local.py`, `opensandbox.py` | `tests/backends/`, `tests/conformance/`, `tests/unit/test_registry.py` |
| `Tool` | `src/rath/flow/tool/`, `src/rath/backend/tool_types.py` | `tests/session/test_tool_registry.py`, `tests/flow/test_flow_tool_user_subclass.py`, `tests/unit/test_flow_tool.py` |
| `AgentParam` | `src/rath/flow/agent_param.py`, `src/rath/flow/agent.py` | `tests/flow/test_workflow_agent.py`, `tests/test_import.py` |
| `Workflow` | `src/rath/flow/workflow.py`, `agent.py`, `session_compressor.py` | `tests/flow/test_workflow_agent.py` |
| `LLM` | `src/rath/llm/`, `src/rath/session/provider_builtin.py` | `tests/llm/`, `tests/session/test_llm_message_wire.py` |

Developer Notes 只描述当前源码已经实现的行为。Roadmap、troubleshooting 和完整应用教程会在后续审计阶段单独补。

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
