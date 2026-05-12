# 工程团队示例（Engineering Agents）

对应目录：`example/engineering_agents/`。

这个例子展示一个工程团队式的 multi-agent nested workflow。它把 lead、architect、backend auth、backend data、frontend 和 QA 拆成不同 `AgentParam`，再通过多个 `Workflow` 类组织成分层执行结构。

## 结构（Structure）

| 文件 | 负责内容 |
| --- | --- |
| `agents.py` | 定义 lead engineer、architect、backend、frontend、QA 的 system prompts。 |
| `workflows.py` | 定义 `BackendPairWorkflow`、`FeatureSquadWorkflow`、`QualityAssuranceWorkflow`、`EngineeringProjectWorkflow`。 |
| `main.py` | CLI 入口，读取 LLM 配置，构造 user session，绑定 local backend 并运行 workflow。 |

## 工作流层次（Workflow Layers）

| 层级 | Class | 角色 |
| --- | --- | --- |
| L1 | `EngineeringProjectWorkflow` | lead plan -> feature squad -> QA。 |
| L2 | `FeatureSquadWorkflow` | architect -> backend pair -> frontend。 |
| L3 | `BackendPairWorkflow` | backend auth -> backend data。 |
| QA | `QualityAssuranceWorkflow` | 读取完整 thread，输出测试计划和风险。 |

这个例子说明 nested workflow 的当前写法：base `Workflow` 自动登记直接赋值的 `AgentParam`，嵌套 workflow 作为普通 Python attribute 组合，并在 `forward(...)` 中显式调用。

## 嵌套 Workflow 代码（Nested Workflow Code）

核心结构来自 `example/engineering_agents/workflows.py`：

```python
class BackendPairWorkflow(Workflow):
    def __init__(self, prov: Provider) -> None:
        super().__init__()
        self.backend_auth = AgentParam(
            Session.from_agent_prompt(BACKEND_AUTH_SYSTEM),
            prov,
        )
        self.backend_data = AgentParam(
            Session.from_agent_prompt(BACKEND_DATA_SYSTEM),
            prov,
        )

    def forward(self, session: Session) -> Session:
        s = run_session_loop(
            session,
            self.backend_auth.agent_session,
            agent_provider=self.backend_auth.provider,
            tools=None,
        )
        return run_session_loop(
            s,
            self.backend_data.agent_session,
            agent_provider=self.backend_data.provider,
            tools=None,
        )
```

外层 workflow 继续组合它：

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

## 运行（Run）

从仓库根目录运行：

```bash
python example/engineering_agents/main.py \
  --goal "Full-stack todo app with auth, DB, React frontend." \
  --workdir .workspace/engineering-agents
```

该例子需要真实 OpenAI-compatible LLM 配置。它默认使用 `OPENAI_DEFAULT_MODEL`，缺省时回退到脚本中的默认模型名。

## 检查结果（What To Inspect）

| 位置 | 看什么 |
| --- | --- |
| stdout | lead、architect、backend、frontend、QA 依次追加到同一个 session。 |
| workflow repr | 直接注册的 `AgentParam` 会出现在 `named_agents()` / `repr(workflow)` 中。 |
| workspace | QA prompt 会要求写入 `ENGINEERING_REVIEW.md`。 |

这个例子适合展示 OpenRath 的高级组合方式：`Workflow` 本身不规定复杂调度策略；开发者用普通 Python 把多个 agent 和子 workflow 组合起来，OpenRath 负责 session、provider、tool 和 sandbox 的运行边界。
