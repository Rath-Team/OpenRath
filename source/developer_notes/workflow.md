# Workflow
`Workflow` 是 OpenRath 的组合层。它把一个或多个 agent 配置组织成可调用对象，并把运行逻辑表达为 `Session -> Session`。

本页说明从单 agent 到 multi-agent 的组织方式、`AgentParam` 的登记规则、nested workflow 的组合方式，以及 session、sandbox、tool 使用痕迹在调用链中的传递。

## 概览
OpenRath 的 workflow 接近 PyTorch module 的写法：

| PyTorch 直觉 | OpenRath 对应 |
| --- | --- |
| `Module.forward(x)` 定义计算 | `Workflow.forward(session)` 定义 agent 编排 |
| 子 module 通过属性挂载 | `AgentParam` 通过属性赋值被登记 |
| tensor 在 module 间传递 | `Session` 在 agent 和 workflow 间传递 |
| module tree 可打印 | `repr(workflow)` 打印已登记 agent |

`Workflow` 的职责很轻：收集直接挂载的 `AgentParam`，提供 `forward(...)` 约定，并让实例可以通过 `workflow(session)` 调用。执行顺序、分支、压缩、工具注入和子 workflow 调用都由开发者在普通 Python 代码里明确写出来。

## 源码地图
| 文件 | 负责内容 |
| --- | --- |
| `src/rath/flow/workflow.py` | `Workflow` base class、attribute registration、`named_agents()`、repr。 |
| `src/rath/flow/agent_param.py` | 可被 workflow 登记的 `AgentParam`。 |
| `src/rath/flow/agent.py` | `Agent` 预设 workflow，封装单 agent loop。 |
| `src/rath/flow/session_compressor.py` | `SessionCompressor` 预设 workflow，封装压缩调用。 |
| `src/rath/session/loop.py` | 执行 LLM loop、工具调用、sandbox 迁移和 lineage 写入。 |
| `example/trading_agents/workflow.py` | 顺序 multi-agent workflow 示例。 |
| `example/engineering_agents/workflows.py` | nested workflow 示例。 |

## 最小 Workflow
继承 `Workflow` 并实现 `forward(self, session) -> Session`：

```python
from rath.flow import Workflow
from rath.session import Session


class IdentityWorkflow(Workflow):
    def forward(self, session: Session) -> Session:
        return session
```

`Workflow.__call__(session)` 直接调用 `forward(session)`。base `forward(...)` 会抛 `NotImplementedError`，所以子类必须定义自己的运行逻辑。

## AgentParam 自动登记
当 `AgentParam` 作为 attribute 赋值给 workflow 时，`Workflow.__setattr__` 会把它记录到 `_agents`：

```python
from rath.flow import AgentParam, Provider, Workflow
from rath.session import Session


class PlanningWorkflow(Workflow):
    def __init__(self):
        super().__init__()
        self.planner = AgentParam(
            Session.from_agent_prompt("Plan the work."),
            Provider(model="gpt-5.5"),
        )
```

这段赋值产生两个结果：

| 结果 | 行为 |
| --- | --- |
| Python attribute | 可以通过 `self.planner` 使用。 |
| workflow registry | 可以通过 `named_agents()` 和 `repr(workflow)` 查看。 |

`named_agents()` 按 attribute name 排序返回 tuple。删除属性时，`Workflow.__delattr__` 会从 `_agents` 删除同名登记项。

## 单 agent 到 multi-agent
最小可运行路径可以直接使用预设 `flow.Agent`：

```python
from rath import flow

agent = flow.Agent(
    system_prompt="Answer clearly.",
    model="gpt-5.5",
)

out = agent(user_session)
```

需要多个角色时，可以把每个角色写成 `AgentParam`，并在 `forward(...)` 中逐个调用 `run_session_loop(...)`：

```python
from rath.flow import AgentParam, Provider, Workflow
from rath.session import Session, run_session_loop


class ReviewWorkflow(Workflow):
    def __init__(self, model: str):
        super().__init__()
        provider = Provider(model=model)
        self.writer = AgentParam(
            Session.from_agent_prompt("Write a first draft."),
            provider,
        )
        self.reviewer = AgentParam(
            Session.from_agent_prompt("Review the draft and tighten it."),
            provider,
        )

    def forward(self, session: Session) -> Session:
        draft = run_session_loop(
            session,
            self.writer.agent_session,
            agent_provider=self.writer.provider,
        )
        return run_session_loop(
            draft,
            self.reviewer.agent_session,
            agent_provider=self.reviewer.provider,
        )
```

第一次 loop 的输出成为第二次 loop 的输入。session graph 会记录每次 loop 的父节点，sandbox handle 会从输入 session 迁移到输出 session。

## 组合单位是 Session
`Workflow` 之间的接口是 `Session`。这使几种组合方式保持一致：

| 组合方式 | 写法 | 适用场景 |
| --- | --- | --- |
| 顺序调用 | `s = step_a(s); s = step_b(s)` | 角色按固定顺序工作。 |
| 分叉探索 | `left = s.fork(); right = s.fork()` | 同一上下文派生多个候选路径。 |
| session 级并行 | `left = pool.submit(...); right = pool.submit(...)` | 多个 fork session 同时进入不同 agent。 |
| 脱离历史 | `clean = s.detach()` | 复用内容但切断 lineage。 |
| 压缩上下文 | `compressor(s)` | 长会话进入下一阶段前缩短历史。 |
| 嵌套 workflow | `s = self.child.forward(s)` | 把复杂流程拆成更小模块。 |

这些操作最终都围绕 session graph 工作。`fork()`、`detach()`、`run_session_loop(...)`、`run_session_compress(...)` 会在输出 session 上写入 lineage；tool result 会作为 chunk 留在 session table 里；sandbox lifecycle 由 session 持有和迁移。

## Session 级并行
OpenRath 的 multi-agent 并行基于 session 分支，而不是特殊的调度 DSL。一个上游 agent 产出 session 后，可以通过 `fork()` 派生多个分支，再用普通 Python 并发工具把这些分支交给不同 agent。

```python
from concurrent.futures import ThreadPoolExecutor


def forward(self, session: Session) -> Session:
    analysed = run_session_loop(
        session,
        self.analyst.agent_session,
        agent_provider=self.analyst.provider,
        tools=[market_tool],
    )

    bear_input = analysed.fork()
    bull_input = analysed.fork()

    with ThreadPoolExecutor(max_workers=2) as pool:
        bear_future = pool.submit(
            run_session_loop,
            bear_input,
            self.researcher_bear.agent_session,
            agent_provider=self.researcher_bear.provider,
            tools=None,
        )
        bull_future = pool.submit(
            run_session_loop,
            bull_input,
            self.researcher_bull.agent_session,
            agent_provider=self.researcher_bull.provider,
            tools=None,
        )
        bear_session = bear_future.result()
        bull_session = bull_future.result()

    # 当前 base Workflow 仍返回一个 Session。
    # 分支聚合策略由 workflow 显式定义，例如提取两个分支的摘要后交给 trader。
    return self._trade_from_branches(bear_session, bull_session)
```

这个模式有三个边界：

| 边界 | 说明 |
| --- | --- |
| lineage | 两个 fork session 都保留同一个 parent，后续 loop 输出会记录各自的 agent parent。 |
| sandbox | `fork()` 复制 backend target，不复制 open handle；并行分支会按需打开自己的 sandbox handle。 |
| 聚合 | 当前没有内置 merge primitive；workflow 需要显式决定如何把多个输出 session 汇总成下一步输入。 |

因此，OpenRath 的并行单位是 session。工具 stream 并发属于 backend 层，`Provider.parallel_tool_calls` 属于 LLM tool-call 参数，二者和 session 级并行是不同层次。

## 预设 Workflow
OpenRath 目前提供两个预设子类：

| Class | 封装内容 | 适合场景 |
| --- | --- | --- |
| `Agent` | 一个 `AgentParam`、一个 tools list、一次 `run_session_loop(...)` | 单 agent 调用、快速接入工具。 |
| `SessionCompressor` | 一个 `AgentParam`、一次 `run_session_compress(...)` | 把长 session 压缩成新的 user-side session。 |

`Agent` 的 `register_tool(...)` 会按工具名去重。`SessionCompressor` 会让模型输出一段新的 user message，压缩结果保留 session lineage，并继续持有输入 session 的 sandbox 配置和 handle。

## Nested Workflow
仓库里的 Engineering Agents 例子展示了 nested workflow：

```python
class EngineeringProjectWorkflow(Workflow):
    def __init__(self, model: str) -> None:
        super().__init__()
        prov = Provider(model=model)
        self.lead = AgentParam(Session.from_agent_prompt(LEAD_ENGINEER_SYSTEM), prov)
        self._squad = FeatureSquadWorkflow(prov)
        self._qa = QualityAssuranceWorkflow(prov)

    def forward(self, session: Session) -> Session:
        s = run_session_loop(
            session,
            self.lead.agent_session,
            agent_provider=self.lead.provider,
            tools=None,
        )
        s = self._squad.forward(s)
        return self._qa.forward(s)
```

当前 base class 只登记直接赋值的 `AgentParam`。`self._squad` 和 `self._qa` 是普通 Python attribute，它们的执行由 `forward(...)` 显式调用。outer workflow 的 `repr(...)` 只展示直接登记的 agent；层级组合由源码结构和调用路径体现。

## Trading Agents 示例
`example/trading_agents/workflow.py` 展示一个固定顺序的多角色流程：

```text
analyst
  researcher_bear
  researcher_bull
  trader
  risk_pm
```

`analyst` 阶段注入 `AlphaVantageGlobalQuoteTool`，后续阶段读取已经进入 session 的 tool result 和 assistant 内容。外部数据工具可以只交给某一个角色使用，工具结果通过 session 传给后续角色。

外部行情 API 只用于演示工具能力。公开示例要求用户显式设置自己的 API key，防止默认 key 被误认为产品能力的一部分。

## Engineering Agents 示例
`example/engineering_agents/workflows.py` 展示分层组合：

| 层级 | Workflow | 执行内容 |
| --- | --- | --- |
| L1 | `EngineeringProjectWorkflow` | lead plan -> feature squad -> QA。 |
| L2 | `FeatureSquadWorkflow` | architect -> backend pair -> frontend。 |
| L3 | `BackendPairWorkflow` | backend auth -> backend data。 |
| QA | `QualityAssuranceWorkflow` | 基于完整 session 做测试和风险检查。 |

该示例展示复杂工程任务的组织方式：每个 workflow 处理自己的局部顺序，父 workflow 把子 workflow 串起来，所有阶段共享同一条 session 传递链。

## Tool 与 Sandbox 边界
在 workflow 里，tool 和 sandbox 仍然通过 `run_session_loop(...)` 生效：

| 事项 | 发生位置 |
| --- | --- |
| 工具列表合并 | 每一次 `run_session_loop(...)` 开始时。 |
| 工具调用记录 | 写入输出 session 的 `tool_result` chunk。 |
| sandbox handle | 从输入 session `take_sandbox()`，再绑定到输出 session。 |
| sandbox backend spec | 跟随输出 session 保存。 |
| lineage | 输出 session 记录 user session 和 agent session 两个父节点。 |

因此，一个 workflow 可以让不同角色使用不同工具；同一个 sandbox 可以随 session 穿过多个角色；后续 agent 能看到前面工具产生的结果。

## 调用路径
```text
workflow(session)
  Workflow.__call__
  subclass.forward(session)
  run_session_loop or child workflow
  returned Session carries new chunks, sandbox, lineage
```

如果使用预设 `Agent`：

```text
flow.Agent.forward(session)
  run_session_loop(
    user_session=session,
    agent_session=self.agent.agent_session,
    agent_provider=self.agent.provider,
    tools=self.tools,
  )
```

如果使用预设 `SessionCompressor`：

```text
flow.SessionCompressor.forward(session)
  run_session_compress(
    user_session=session,
    agent_session=self.agent.agent_session,
    agent_provider=self.agent.provider,
  )
```

## 当前边界
| 行为 | 当前实现 |
| --- | --- |
| attribute registration | 只有赋值为 `AgentParam` 的 attribute 会进入 `_agents`。 |
| deletion | `__delattr__` 会把同名 agent 从 `_agents` 移除。 |
| ordering | `named_agents()` 按 attribute name 排序。 |
| base execution | `Workflow.forward(...)` 抛 `NotImplementedError`。 |
| nested workflow | base class 不自动登记子 workflow。 |
| async support | 当前 `Workflow.forward(...)` 是同步接口。 |
| scheduling policy | 顺序、分支、重试和并发策略由用户在 Python 代码中表达。 |

## 读源码时的检查点
1. 在 `workflow.py` 里查看 `__slots__ = ("_agents",)` 和 `__setattr__`。
2. 在 `workflow.py` 里查看 `named_agents()` 的排序规则。
3. 在 `agent.py` 里查看 `Agent.forward(...)` 如何调用 `run_session_loop(...)`。
4. 在 `session_compressor.py` 里查看压缩 workflow 如何调用 `run_session_compress(...)`。
5. 在 `example/trading_agents/workflow.py` 里查看固定顺序 multi-agent。
6. 在 `example/engineering_agents/workflows.py` 里查看 nested workflow。
7. 在 `tests/flow/test_workflow_agent.py` 里查看 workflow registration 和 sandbox 迁移的测试。

## 测试覆盖
| 行为 | 测试 |
| --- | --- |
| workflow registration and agent call | `tests/flow/test_workflow_agent.py` |
| import contract | `tests/test_import.py` |
| session compressor live behavior | `tests/integration/test_session_compress_real.py` |

## 相关页面
| 页面 | 内容 |
| --- | --- |
| [AgentParam](agent_param.md) | agent-side session、provider 和 request assembly。 |
| [Trading Agents](../tutorial/examples/trading_agents.md) | 顺序多角色 workflow，包含外部行情工具。 |
| [Engineering Agents](../tutorial/examples/engineering_agents.md) | 嵌套 workflow，展示工程团队式 agent 编排。 |
