# 工作流（Workflow）

`Workflow` 是 OpenRath 的高级组合组件。它把 agent 参数注册为成员，并把 `Session -> Session` 的运行逻辑放在 `forward(...)` 中。

本页回答：`Workflow` 如何组合多个 `AgentParam`，nested workflow 如何复用 session graph，以及 session、sandbox、tool 边界如何随调用链被维护。

## 源码地图（Source Map）

| 文件 | 负责内容 |
| --- | --- |
| `src/rath/flow/workflow.py` | `Workflow` base class、attribute registration、repr。 |
| `src/rath/flow/agent.py` | `Agent` preset workflow。 |
| `src/rath/flow/session_compressor.py` | `SessionCompressor` preset workflow。 |
| `src/rath/flow/agent_param.py` | workflow 可注册的 `AgentParam`。 |

## 基础类型（Base Type）

```python
from rath.flow import Workflow
from rath.session import Session


class MyWorkflow(Workflow):
    def forward(self, session: Session) -> Session:
        return session
```

`Workflow.__call__(session)` 会调用 `forward(session)`。

## AgentParam 注册（AgentParam Registration）

当 `AgentParam` 作为 attribute 赋值给 workflow 时，`Workflow.__setattr__` 会把它记录到 `_agents`。

```python
from rath import flow
from rath.flow import AgentParam, Provider, Workflow
from rath.session import Session


class TwoStepWorkflow(Workflow):
    def __init__(self):
        super().__init__()
        self.planner = AgentParam(
            Session.from_agent_prompt("Plan the work."),
            Provider(model="gpt-5.5"),
        )
        self.writer = AgentParam(
            Session.from_agent_prompt("Write the final answer."),
            Provider(model="gpt-5.5"),
        )
```

`named_agents()` 返回通过 attribute assignment 注册的 agent params。`repr(workflow)` 会以类似 module tree 的形式展示成员。

## 组合方式（Composition）

Workflow 的组合单位是 `Session`。开发者可以在 `forward(...)` 中顺序调用 agent、分叉 session、压缩上下文，或把一个 workflow 的输出交给另一个 workflow。

```python
class DraftAndCompress(Workflow):
    def __init__(self):
        super().__init__()
        self.draft = flow.Agent("Draft an answer.", model="gpt-5.5")
        self.compress = flow.SessionCompressor(
            "Compress the session into a short user message.",
            model="gpt-5.5",
        )

    def forward(self, session: Session) -> Session:
        drafted = self.draft(session)
        return self.compress(drafted)
```

Session graph 由被调用的 primitives 维护：`fork()`、`detach()`、`run_session_loop(...)`、`run_session_compress(...)` 会在输出 session 上写入 lineage。

## 多智能体示例（Multi-Agent Examples）

仓库里的 `example/` 目录现在包含两个 multi-agent workflow。它们不是单独的调度引擎，而是普通 Python `Workflow` 子类对 `AgentParam` 和 `run_session_loop(...)` 的组合。

| Example | 文件 | 组合方式 |
| --- | --- | --- |
| Trading Agents | `example/trading_agents/workflow.py` | `analyst -> researcher_bear -> researcher_bull -> trader -> risk_pm` 顺序执行。 |
| Engineering Agents | `example/engineering_agents/workflows.py` | `EngineeringProjectWorkflow` 组合 `FeatureSquadWorkflow`，后者再组合 `BackendPairWorkflow`。 |

Trading Agents 使用一个自定义 `FlowToolCall` 读取 Alpha Vantage quote，然后把包含 tool result 的 session 继续传给后续角色。Engineering Agents 展示 nested workflow：base `Workflow` 自动登记直接赋值的 `AgentParam`，嵌套 workflow 作为普通 attribute 由 `forward(...)` 显式调用。

这两个例子说明 OpenRath 的 multi-agent 路径：agent 角色由 `AgentParam` 表示，执行顺序由 `Workflow.forward(...)` 决定，跨角色上下文由同一个 `Session` 继续流动。

## 预设工作流（Preset Workflows）

| Class | 用途 |
| --- | --- |
| `Agent` | 单 agent session loop。 |
| `SessionCompressor` | 对已有 session 做一次压缩调用。 |

这些预设类覆盖常用路径。复杂 workflow 可以直接继承 `Workflow` 并组合它们。

## 调用路径（Call Path）

```text
workflow(session)
  -> Workflow.__call__
  -> subclass.forward(session)
  -> optional Agent.forward / SessionCompressor.forward
  -> run_session_loop / run_session_compress
  -> returned Session carries lineage
```

## 边界条件（Boundary Conditions）

| 行为 | 当前实现 |
| --- | --- |
| attribute registration | 只有赋值为 `AgentParam` 的 attribute 会进入 `_agents`。 |
| deletion | `__delattr__` 会把同名 agent 从 `_agents` 移除。 |
| ordering | `named_agents()` 按 attribute name 排序。 |
| execution | base `Workflow.forward(...)` 抛 `NotImplementedError`。 |
| nested workflow | 当前 base class 不自动注册 nested workflow，只注册 `AgentParam`。 |

## 测试覆盖（Test Coverage）

| 行为 | 测试 |
| --- | --- |
| workflow registration and agent call | `tests/flow/test_workflow_agent.py` |
| import contract | `tests/test_import.py` |
| session compressor live behavior | `tests/integration/test_session_compress_real.py` |

## 相关页面（See Also）

| 页面 | 内容 |
| --- | --- |
| [Trading Agents](../tutorial/examples/trading_agents.md) | 顺序多角色 workflow，包含外部行情工具。 |
| [Engineering Agents](../tutorial/examples/engineering_agents.md) | 嵌套 workflow，展示工程团队式 agent 编排。 |
