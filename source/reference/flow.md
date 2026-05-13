(pkg-flow)=
# `rath.flow`

Workflow composition layer. `Workflow` organizes `Session -> Session` transforms, `AgentParam` stores the agent-side session and provider, and preset workflows wrap common paths.

## Source
| Module | Source |
| --- | --- |
| `rath.flow.workflow` | `src/rath/flow/workflow.py` |
| `rath.flow.agent_param` | `src/rath/flow/agent_param.py` |
| `rath.flow.agent` | `src/rath/flow/agent.py` |
| `rath.flow.compressor` | `src/rath/flow/compressor.py` |

## Public contract
### `Workflow`

| Method | Returns | Behavior |
| --- | --- | --- |
| `forward(session)` | `Session` | Execution logic implemented by subclasses. |
| `__call__(session)` | `Session` | Calls `forward(session)`. |
| `named_agents()` | `tuple[tuple[str, AgentParam], ...]` | Returns agent params registered as attributes. |

When an `AgentParam` is assigned to a workflow as an attribute, `Workflow.__setattr__` adds it to `_agents`.

### `AgentParam`

| Field | Type | Description |
| --- | --- | --- |
| `agent_session` | `Session` | Agent/system transcript. |
| `provider` | `Provider` | Model and request parameters. |

### Preset workflows
| Class | Constructor arguments | Behavior |
| --- | --- | --- |
| `Agent` | `system_prompt`, `provider`, `tools=None`, `chunk_print=None` | Creates an agent session and stores the supplied provider. `forward(...)` calls `run_session_loop(...)`. |
| `Compressor` | `compress_instruction`, `provider`, `chunk_print=None` | `forward(...)` calls `run_session_compress(...)`. |

`Agent.register_tool(tool)` adds tools and deduplicates by name. `Agent.unregister_tool(tool_name)` removes the tool with the same name.

### Runnable workflow examples
| Example | Path | Description |
| --- | --- | --- |
| Trading Agents | `example/trading_agents/` | Sequential multi-role workflow with an analyst, researchers, trader, risk/PM, and a market data tool. |
| Engineering Agents | `example/engineering_agents/` | Nested workflow showing layered composition across lead, feature squad, backend pair, frontend, and QA roles. |

These examples use the public `Workflow`, `AgentParam`, `Provider`, and `run_session_loop(...)` APIs, so they are useful source references for multi-agent composition.

## Autodoc
```{eval-rst}
.. autoclass:: rath.flow.Workflow
   :members:

.. autoclass:: rath.flow.AgentParam
   :members:

.. autoclass:: rath.flow.Agent
   :members:

.. autoclass:: rath.flow.Compressor
   :members:
```

[← API Reference](index.md)
