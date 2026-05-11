(pkg-flow)=
# `rath.flow`

工作流组合层。`Workflow` 负责组织 `Session -> Session` 变换，`AgentParam` 保存 agent-side session 与 provider，预设 workflow 封装常用路径。

## 源码
| 模块 | 源码 |
| --- | --- |
| `rath.flow.workflow` | `src/rath/flow/workflow.py` |
| `rath.flow.agent_param` | `src/rath/flow/agent_param.py` |
| `rath.flow.agent` | `src/rath/flow/agent.py` |
| `rath.flow.session_compressor` | `src/rath/flow/session_compressor.py` |

## 公共契约
### `Workflow`

| 方法 | 返回 | 行为 |
| --- | --- | --- |
| `forward(session)` | `Session` | 子类实现的执行逻辑。 |
| `__call__(session)` | `Session` | 调用 `forward(session)`。 |
| `named_agents()` | `tuple[tuple[str, AgentParam], ...]` | 返回 attribute 注册的 agent params。 |

当 `AgentParam` 作为 attribute 赋值给 workflow 时，`Workflow.__setattr__` 会将其加入 `_agents`。

### `AgentParam`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `agent_session` | `Session` | agent/system transcript。 |
| `provider` | `Provider` | model 和请求参数。 |

### 预设工作流
| Class | 构造参数 | 行为 |
| --- | --- | --- |
| `Agent` | `system_prompt`, `model`, `tools=None` | 创建 agent session 和 provider，`forward(...)` 调用 `run_session_loop(...)`。 |
| `SessionCompressor` | `compress_instruction`, `model` | `forward(...)` 调用 `run_session_compress(...)`。 |

`Agent.register_tool(tool)` 会按 name 去重添加工具；`Agent.unregister_tool(tool_name)` 会移除同名工具。

### 可运行工作流示例
| Example | 路径 | 说明 |
| --- | --- | --- |
| Trading Agents | `example/trading_agents/` | 顺序多角色 workflow，包含 analyst、researchers、trader、risk/PM 和一个市场数据工具。 |
| Engineering Agents | `example/engineering_agents/` | 嵌套 workflow，展示 lead、feature squad、backend pair、frontend、QA 的分层组合。 |

这些例子使用 public `Workflow`、`AgentParam`、`Provider` 和 `run_session_loop(...)`，适合作为 multi-agent 组合的源码参考。

## 自动文档
```{eval-rst}
.. autoclass:: rath.flow.Workflow
   :members:

.. autoclass:: rath.flow.AgentParam
   :members:

.. autoclass:: rath.flow.Agent
   :members:

.. autoclass:: rath.flow.SessionCompressor
   :members:
```

[← API Reference](index.md)
