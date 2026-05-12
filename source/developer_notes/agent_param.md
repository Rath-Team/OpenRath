# Agent 参数（Agent Param）

`AgentParam` 保存 agent-side session 和 LLM request 参数。它是 workflow 中可被注册和打印的 agent 配置对象。

本页回答：`AgentParam` 为什么只维护 system prompt、provider 和 memory-like 数据，session loop 如何把 agent session 与 user session 拼成一次完整请求。

## 源码地图（Source Map）

| 文件 | 负责内容 |
| --- | --- |
| `src/rath/flow/agent_param.py` | `AgentParam` dataclass、read-only `data` mapping、repr。 |
| `src/rath/flow/agent.py` | `Agent` convenience workflow。 |
| `src/rath/llm/provider.py` | `Provider` request options。 |
| `src/rath/session/loop.py` | agent session 与 user session 的 request assembly。 |

## 结构（Structure）

当前 `AgentParam` 字段：

| 字段 | 类型 | 作用 |
| --- | --- | --- |
| `agent_session` | `Session` | 通常由 `Session.from_agent_prompt(...)` 创建，保存 system prompt。 |
| `provider` | `Provider` | 保存 model、temperature、tool choice 等请求参数。 |

```python
from rath.flow import AgentParam, Provider
from rath.session import Session

param = AgentParam(
    agent_session=Session.from_agent_prompt("You are concise."),
    provider=Provider(model="gpt-5.5"),
)
```

`param.data` 返回只读 mapping，包含 `agent_session` 和 `provider`。

## 请求组装（Request Assembly）

`run_session_loop(...)` 接收 user session、agent session 和 provider。

```python
from rath.session import run_session_loop

out = run_session_loop(
    user_session=user,
    agent_session=param.agent_session,
    agent_provider=param.provider,
)
```

loop 构造 request 时会把 agent session rows 放到 user session rows 前面。输出 session 以 user-side rows 为起点，随后追加 assistant 和 `tool_result` rows。

## Agent 封装（Agent Wrapper）

`flow.Agent` 是预设 workflow。它内部创建一个 `AgentParam`，并维护一个工具列表。

```python
from rath import flow

agent = flow.Agent(
    system_prompt="Use tools when useful.",
    model="gpt-5.5",
)

out = agent(user)
```

`Agent.forward(...)` 调用 `run_session_loop(...)`。`register_tool(...)` 和 `unregister_tool(...)` 修改 agent 的工具列表。

## 边界（Boundary）

当前 `AgentParam` 只包含 `agent_session` 和 `provider`。更复杂的 memory、routing、policy 等状态可以由 workflow 子类或自定义数据结构维护。

## 调用路径（Call Path）

```text
flow.Agent.__init__
  -> Session.from_agent_prompt(system_prompt)
  -> Provider(model=model)
  -> AgentParam(agent_session, provider)

flow.Agent.forward
  -> run_session_loop(
       user_session=session,
       agent_session=self.agent.agent_session,
       agent_provider=self.agent.provider,
       tools=self.tools,
     )
```

## 边界条件（Boundary Conditions）

| 行为 | 当前实现 |
| --- | --- |
| `AgentParam.data` | 返回 `MappingProxyType`，调用者获得只读 view。 |
| `Agent.register_tool(tool)` | 同名工具已存在时直接返回。 |
| `Agent.unregister_tool(name)` | 过滤掉同名工具。 |
| memory | 当前 `AgentParam` 无 memory 字段。 |
| system prompt | 作为 `agent_session` 的 system chunk 保存。 |

## 测试覆盖（Test Coverage）

| 行为 | 测试 |
| --- | --- |
| import contract | `tests/test_import.py` |
| workflow agent loop | `tests/flow/test_workflow_agent.py` |
| custom tool through agent/loop | `tests/flow/test_flow_tool_user_subclass.py` |
