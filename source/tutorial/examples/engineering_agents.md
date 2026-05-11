# Engineering Agents

对应目录：`example/engineering_agents/`。

本示例展示工程团队式 nested workflow。lead、architect、backend auth、backend data、frontend 和 QA 分别由 `AgentParam` 表达，再通过多个 `Workflow` 类组成分层执行结构。

## 覆盖内容
| 主题 | 结果 |
| --- | --- |
| nested workflow | 父 workflow 调用子 workflow，子 workflow 再调用更小 workflow。 |
| direct registration | 直接赋值的 `AgentParam` 会被当前 workflow 登记。 |
| ordinary attributes | 子 workflow 作为普通 attribute 保存，并在 `forward(...)` 中调用。 |
| session pipeline | 所有角色沿同一个 session 继续追加上下文。 |
| session-level parallel | 没有上下游依赖的子任务可以从同一个 session fork 后并行运行。 |
| engineering decomposition | 复杂工程任务被拆成 lead、architect、backend、frontend、QA。 |

## 目录结构
| 文件 | 负责内容 |
| --- | --- |
| `agents.py` | 定义 lead engineer、architect、backend、frontend、QA 的 system prompts。 |
| `workflows.py` | 定义 `BackendPairWorkflow`、`FeatureSquadWorkflow`、`QualityAssuranceWorkflow`、`EngineeringProjectWorkflow`。 |
| `main.py` | CLI 入口，读取 LLM 配置，构造 user session，绑定 local backend 并运行 workflow。 |

## 工作流层次
| 层级 | Class | 执行内容 |
| --- | --- | --- |
| L1 | `EngineeringProjectWorkflow` | lead plan -> feature squad -> QA。 |
| L2 | `FeatureSquadWorkflow` | architect -> backend pair -> frontend。 |
| L3 | `BackendPairWorkflow` | backend auth -> backend data。 |
| QA | `QualityAssuranceWorkflow` | 基于完整 session 输出测试计划和风险。 |

当前 nested workflow 的写法有三条规则：直接挂在当前 workflow 上的 `AgentParam` 会被登记；子 workflow 按普通 Python attribute 保存；执行顺序由 `forward(...)` 明确写出。

## Session 级并行
Engineering Agents 也可以用 session 分支表达并行开发。当前示例里的 `BackendPairWorkflow` 顺序运行 auth backend 和 data backend；如果两个子任务已经从 architect 阶段拿到足够上下文，就可以从同一个 session fork 出两条 branch 并行执行：

```python
from concurrent.futures import ThreadPoolExecutor


auth_input = session.fork()
data_input = session.fork()

with ThreadPoolExecutor(max_workers=2) as pool:
    auth_future = pool.submit(
        run_session_loop,
        auth_input,
        self.backend_auth.agent_session,
        agent_provider=self.backend_auth.provider,
        tools=None,
    )
    data_future = pool.submit(
        run_session_loop,
        data_input,
        self.backend_data.agent_session,
        agent_provider=self.backend_data.provider,
        tools=None,
    )
    auth_session = auth_future.result()
    data_session = data_future.result()
```

这种写法不会把两个分支自动合并成一个 transcript。workflow 需要显式定义下一步输入，例如让父 workflow 提取两个分支的摘要，再交给 frontend 或 QA agent。OpenRath 负责记录 fork 和 loop 的 lineage，并保证每个分支的 sandbox handle 按 session 生命周期独立维护。

## BackendPairWorkflow
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

关键点：

| 行 | 解释 |
| --- | --- |
| `self.backend_auth = AgentParam(...)` | auth backend 角色被登记到当前 workflow。 |
| `self.backend_data = AgentParam(...)` | data backend 角色也被登记。 |
| `s = run_session_loop(...)` | auth 的输出 session 进入 data 阶段。 |
| `tools=None` | 角色仍可使用内置工具，未额外添加自定义工具。 |

## 外层组合
外层 workflow 继续组合子 workflow：

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

关键点：

| 行 | 解释 |
| --- | --- |
| `self.lead = AgentParam(...)` | lead 是当前 workflow 的直接 agent。 |
| `self._squad = FeatureSquadWorkflow(prov)` | 子 workflow 作为普通 attribute。 |
| `self._qa = QualityAssuranceWorkflow(prov)` | QA 子 workflow 也作为普通 attribute。 |
| `self._squad.forward(s)` | 父 workflow 显式调用子 workflow。 |
| `return self._qa.forward(s)` | QA 阶段接收完整 session。 |

## 运行
从仓库根目录运行：

```bash
python example/engineering_agents/main.py \
  --goal "Full-stack todo app with auth, DB, React frontend." \
  --workdir .workspace/engineering-agents
```

该例子需要真实 OpenAI-compatible LLM 配置。脚本会读取默认模型配置；缺省时回退到脚本中的默认模型名。

## 观察结果
| 位置 | 看什么 |
| --- | --- |
| stdout | lead、architect、backend、frontend、QA 依次追加到同一个 session。 |
| workflow repr | 直接注册的 `AgentParam` 会出现在 `named_agents()` 和 `repr(workflow)` 中。 |
| workspace | QA prompt 会要求写入 `ENGINEERING_REVIEW.md`。 |
| chunk table | 可以看到各角色 assistant message 的顺序。 |

## 常见问题
| 现象 | 检查方向 |
| --- | --- |
| LLM 请求失败 | 检查模型网关配置。 |
| workspace 没有输出文件 | 检查模型是否实际调用了写文件工具。 |
| repr 里看不到子 workflow | 当前 base class 只登记直接挂载的 `AgentParam`。 |
| 输出内容重复 | 检查每个角色的 system prompt 分工。 |

## 练习
1. 在 `FeatureSquadWorkflow` 中新增一个 security reviewer。
2. 把 QA 阶段改成 `SessionCompressor` 之前的一步，先压缩再输出报告。
3. 打印每个阶段后的 session row 数量，观察上下文如何增长。
