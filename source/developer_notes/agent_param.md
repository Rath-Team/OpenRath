# AgentParam
`AgentParam` 保存一个 agent 的系统上下文和模型请求参数。workflow 可以像登记子模块一样登记 agent 配置；执行仍由 `Session` 和 `run_session_loop(...)` 完成。

本页说明 agent 的系统提示词保存位置、模型参数进入请求的路径、`flow.Agent` 的封装内容，以及 loop 结束后返回 user session 的原因。

## 概览
在 OpenRath 里，agent 的身份由两部分组成：

| 部分 | 当前实现 | 作用 |
| --- | --- | --- |
| 系统上下文 | `agent_session` | 保存 system prompt，对 LLM 来说是请求开头的上下文。 |
| 模型参数 | `provider` | 保存 model、temperature、tool choice 等 OpenAI-compatible 请求参数。 |

`AgentParam` 本身只维护这两部分数据。它可以被 `Workflow` 自动登记、打印和枚举；调用 LLM、执行工具、迁移 sandbox、写 session graph 的工作发生在 `run_session_loop(...)` 里。

这条边界决定了三个对象的分工：`AgentParam` 描述 agent 身份，`Session` 描述当前任务状态，`Workflow.forward(...)` 描述执行顺序。

## 源码地图
| 文件 | 负责内容 |
| --- | --- |
| `src/rath/flow/agent_param.py` | `AgentParam` dataclass、`data` 只读 view、repr。 |
| `src/rath/flow/agent.py` | `Agent` 预设 workflow，负责创建 `AgentParam` 并调用 loop。 |
| `src/rath/llm/provider.py` | `Provider`，保存模型和采样参数。 |
| `src/rath/session/loop.py` | 把 agent session 和 user session 拼成请求，并返回新的 user session。 |
| `src/rath/flow/workflow.py` | attribute assignment 时登记 `AgentParam`。 |

## 数据结构
当前 `AgentParam` 是一个带 slots 的 dataclass，只有两个字段：

```python
from rath.flow import AgentParam, Provider
from rath.session import Session

param = AgentParam(
    agent_session=Session.from_agent_prompt("You are concise."),
    provider=Provider(model="gpt-5.5"),
)
```

| 字段 | 类型 | 典型来源 | 运行时含义 |
| --- | --- | --- | --- |
| `agent_session` | `Session` | `Session.from_agent_prompt(...)` | 放在请求开头的系统上下文。 |
| `provider` | `Provider` | `Provider(model=...)` | 传给 LLM request builder 的模型配置。 |

`param.data` 返回 `MappingProxyType`，内容是 `agent_session` 和 `provider`。调用者可以读这个 mapping，但不能通过它改写底层字段。

## 为什么系统提示词也是 Session
`Session.from_agent_prompt(...)` 会创建一个只包含 system chunk 的 session。这样做带来三个直接好处：

| 好处 | 对应行为 |
| --- | --- |
| 请求组装统一 | system、user、assistant、tool result 都能通过 `chunk_table_to_messages(...)` 转成 LLM message。 |
| lineage 可追踪 | `run_session_loop(...)` 会把 user session 和 agent session 都登记为输出 session 的父节点。 |
| agent 可复用 | 同一个 `agent_session` 可以反复和不同 user session 拼接，输出仍只返回 user-side 结果。 |

实际请求里，loop 会先读取 `agent_session.chunk_table`，再读取 `user_session.chunk_table`，然后构造模型请求：

```text
request messages
  system rows from agent_session
  user / assistant / tool rows from user_session
```

输出 session 从 user-side rows 开始，随后追加新的 assistant rows 和 tool result rows。agent 的 system rows 参与请求，但不会被复制进输出 session。

## Provider 如何进入请求
`Provider` 保存 OpenAI-compatible chat completion 的可选参数。当前字段包括 `model`、`temperature`、`top_p`、`max_tokens`、`tool_choice`、`parallel_tool_calls`、`response_format`、`reasoning_effort`、`verbosity`、`extra_create_args` 等。

`run_session_loop(...)` 会把 `Provider` 交给 `provider_into_chat_request(...)`：

```python
from rath.session import run_session_loop

out = run_session_loop(
    user_session=user,
    agent_session=param.agent_session,
    agent_provider=param.provider,
)
```

请求中的 `messages` 和 `tools` 由 loop 根据 session 与 tool table 生成；模型、采样、tool choice 等选项来自 `Provider`。这让 agent 配置和当前任务上下文保持分离。

## 在 Workflow 中登记
把 `AgentParam` 赋值给 `Workflow` attribute 时，`Workflow.__setattr__` 会把它放入 `_agents`：

```python
from rath.flow import AgentParam, Provider, Workflow
from rath.session import Session


class ReviewerWorkflow(Workflow):
    def __init__(self):
        super().__init__()
        self.reviewer = AgentParam(
            Session.from_agent_prompt("Review the implementation."),
            Provider(model="gpt-5.5"),
        )
```

这会影响两个开发体验：

| 行为 | 说明 |
| --- | --- |
| `named_agents()` | 返回通过 attribute assignment 注册的 agent params。 |
| `repr(workflow)` | 以接近 PyTorch module tree 的形式打印已登记 agent。 |

登记行为只发生在 `AgentParam` 上。普通字段、工具列表、executor、子 workflow 都按 Python attribute 保存。

## `flow.Agent` 封装了什么
`flow.Agent` 是最常用的单 agent workflow。它在初始化时创建一个 `AgentParam`，并保存一组工具实例：

```python
from rath import flow

agent = flow.Agent(
    system_prompt="Use tools when useful.",
    model="gpt-5.5",
)

out = agent(user)
```

内部结构：

```text
flow.Agent.__init__
  Session.from_agent_prompt(system_prompt)
  Provider(model=model)
  AgentParam(agent_session, provider)
  tools list

flow.Agent.forward
  run_session_loop(user_session, agent_session, agent_provider, tools)
```

`register_tool(tool)` 会按工具名去重，已有同名工具时直接返回。`unregister_tool(name)` 会过滤掉同名工具。工具暴露给模型的步骤发生在 `run_session_loop(...)` 合并 tool table 时。

## 什么时候直接使用 AgentParam
单 agent 调用通常使用 `flow.Agent`。multi-agent workflow 通常直接使用 `AgentParam`，执行顺序在 `forward(...)` 中逐步展开：

```python
from rath.flow import AgentParam, Provider, Workflow
from rath.session import Session, run_session_loop


class TwoPassWorkflow(Workflow):
    def __init__(self, model: str):
        super().__init__()
        provider = Provider(model=model)
        self.planner = AgentParam(
            Session.from_agent_prompt("Plan the task."),
            provider,
        )
        self.writer = AgentParam(
            Session.from_agent_prompt("Write the answer from the plan."),
            provider,
        )

    def forward(self, session: Session) -> Session:
        planned = run_session_loop(
            session,
            self.planner.agent_session,
            agent_provider=self.planner.provider,
        )
        return run_session_loop(
            planned,
            self.writer.agent_session,
            agent_provider=self.writer.provider,
        )
```

这段代码里，`planner` 和 `writer` 各自有独立 system prompt。第二次 loop 接收第一次 loop 的输出 session，所以 planner 的 assistant 内容会成为 writer 的输入上下文。

## 输出 session 的边界
`run_session_loop(...)` 返回的新 session 会继承 user-side 历史，并追加模型产生的新内容。它还会把 sandbox handle 从输入 session 迁移到输出 session。

| 输入 | 参与请求 | 出现在输出 session |
| --- | --- | --- |
| `agent_session` | 是 | 否 |
| `user_session` | 是 | 是 |
| assistant response | 新产生 | 是 |
| tool result | 工具被调用时产生 | 是 |
| sandbox handle | 由 user session 提供 | 迁移到输出 session |

所以，agent 的系统提示词不会污染用户侧上下文。一个 workflow 连续调用多个 agent 时，跨角色流动的是 user session，而每个 agent 的 system prompt 只在它自己的那次请求里生效。

## 当前边界
| 行为 | 当前实现 |
| --- | --- |
| 字段数量 | `AgentParam` 只有 `agent_session` 和 `provider`。 |
| memory | 当前没有单独 memory 字段；长期记忆可以先由 workflow 或 session 内容表达。 |
| 执行能力 | `AgentParam` 没有 `forward(...)`；执行由 `Workflow`、`Agent` 或 `run_session_loop(...)` 完成。 |
| `data` | 返回只读 mapping，但不做深拷贝。 |
| provider 共享 | 多个 `AgentParam` 可以共享同一个 `Provider` 实例。 |
| system prompt | 通常通过 `Session.from_agent_prompt(...)` 创建。 |

## 读源码时的检查点
1. 在 `agent_param.py` 里确认 `AgentParam` 的字段和 `data` 行为。
2. 在 `workflow.py` 里查看 `__setattr__` 如何登记 `AgentParam`。
3. 在 `agent.py` 里查看 `flow.Agent` 如何从 `system_prompt` 和 `model` 创建 `AgentParam`。
4. 在 `loop.py` 里查看 `head = chunk_table_to_messages(agent_session.chunk_table)` 和 `tail = chunk_table_to_messages(...)` 的请求拼接顺序。
5. 在 `loop.py` 里查看输出 session 如何设置 `parent_session_ids=(user_session.id, agent_session.id)`。

## 测试覆盖
| 行为 | 测试 |
| --- | --- |
| import contract | `tests/test_import.py` |
| workflow agent registration and loop | `tests/flow/test_workflow_agent.py` |
| custom tool through agent/loop | `tests/flow/test_flow_tool_user_subclass.py` |
