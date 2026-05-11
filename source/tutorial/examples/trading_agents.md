# Trading Agents

对应目录：`example/trading_agents/`。

本示例展示 TradingAgents-style 的顺序多角色 workflow。它使用真实 LLM 配置，并把 Alpha Vantage quote API 包装成 `FlowToolCall`：analyst agent 先调用市场数据工具，随后同一个 `Session` 继续交给后续角色处理。

## 覆盖内容
| 主题 | 结果 |
| --- | --- |
| 顺序 multi-agent | 五个角色按固定顺序处理同一个 session。 |
| agent identity | 每个角色都是一个 `AgentParam`，拥有自己的 system prompt。 |
| 外部数据工具 | analyst 阶段独享 `AlphaVantageGlobalQuoteTool`。 |
| session continuity | 后续角色读取前面角色留下的 assistant rows 和 tool results。 |
| session-level parallel | analyst 输出后可以 fork 出 bear/bull 两条并行研究分支。 |
| workspace output | 各角色被提示写入自己的报告文件。 |

## 目录结构
| 文件 | 负责内容 |
| --- | --- |
| `agents.py` | 定义 analyst、bear researcher、bull researcher、trader、risk PM 的 system prompts。 |
| `tools.py` | 定义 `AlphaVantageGlobalQuoteTool`，暴露 `alpha_vantage_global_quote`。 |
| `workflow.py` | 定义 `TradingAgentsWorkflow`，按顺序运行五个 agent。 |
| `_env.py` | 加载 OpenAI-compatible LLM 配置，并要求显式设置 Alpha Vantage key。 |
| `main.py` | CLI 入口，构造 user session、绑定 local backend、运行 workflow。 |

## Agent 顺序
| 顺序 | Agent | 行为 |
| --- | --- | --- |
| 1 | analyst | 调用 `alpha_vantage_global_quote`，形成市场数据和初步分析。 |
| 2 | researcher_bear | 基于已有 session 提出风险和负面论点。 |
| 3 | researcher_bull | 基于同一 session 提出正面论点。 |
| 4 | trader | 整合研究内容，输出交易建议。 |
| 5 | risk_pm | 审核 trader proposal，给出风险控制意见。 |

每一步都调用 `run_session_loop(...)`。输出 `Session` 会继续交给下一步，因此后续角色可以读取前面角色留下的 assistant chunks、tool results 和文件写入意图。

## Session 级并行
当前示例为了便于阅读，按顺序运行 bear researcher 和 bull researcher。实际 workflow 可以在 analyst 阶段之后 fork 两个 session，让两位 researcher 并行工作：

```python
from concurrent.futures import ThreadPoolExecutor


market_tools = [AlphaVantageGlobalQuoteTool()]
analyst_session = run_session_loop(
    session,
    self.analyst.agent_session,
    agent_provider=self.analyst.provider,
    tools=market_tools,
)

bear_input = analyst_session.fork()
bull_input = analyst_session.fork()

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
```

这里的并行单位是 `Session`。`fork()` 会复制 analyst 阶段已经形成的 transcript 和 backend target，但不会复制已经打开的 sandbox handle。两个 researcher branch 会产生两条独立 lineage，后续 trader 阶段再由 workflow 显式决定如何汇总这两条 branch，例如提取两边最后的 assistant message，组成新的 user session 交给 trader。

## Workflow 代码
核心结构来自 `example/trading_agents/workflow.py`：

```python
class TradingAgentsWorkflow(Workflow):
    def __init__(self, model: str) -> None:
        super().__init__()
        prov = Provider(model=model)
        self.analyst = AgentParam(Session.from_agent_prompt(ANALYST_SYSTEM), prov)
        self.researcher_bear = AgentParam(
            Session.from_agent_prompt(RESEARCHER_BEAR_SYSTEM),
            prov,
        )
        self.researcher_bull = AgentParam(
            Session.from_agent_prompt(RESEARCHER_BULL_SYSTEM),
            prov,
        )
        self.trader = AgentParam(Session.from_agent_prompt(TRADER_SYSTEM), prov)
        self.risk_pm = AgentParam(Session.from_agent_prompt(RISK_PM_SYSTEM), prov)

    def forward(self, session: Session) -> Session:
        market_tools = [AlphaVantageGlobalQuoteTool()]
        s = run_session_loop(
            session,
            self.analyst.agent_session,
            agent_provider=self.analyst.provider,
            tools=market_tools,
        )
        s = run_session_loop(
            s,
            self.researcher_bear.agent_session,
            agent_provider=self.researcher_bear.provider,
            tools=None,
        )
        s = run_session_loop(
            s,
            self.researcher_bull.agent_session,
            agent_provider=self.researcher_bull.provider,
            tools=None,
        )
        s = run_session_loop(
            s,
            self.trader.agent_session,
            agent_provider=self.trader.provider,
            tools=None,
        )
        return run_session_loop(
            s,
            self.risk_pm.agent_session,
            agent_provider=self.risk_pm.provider,
            tools=None,
        )
```

关键点：

| 行 | 解释 |
| --- | --- |
| `prov = Provider(model=model)` | 五个角色共享同一个模型配置。 |
| `self.analyst = AgentParam(...)` | 赋值时被 `Workflow` 登记。 |
| `market_tools = [AlphaVantageGlobalQuoteTool()]` | 市场数据工具只传给 analyst。 |
| `s = run_session_loop(s, ...)` | 每个角色接收前一个角色输出的 session。 |
| `tools=None` | 后续角色使用内置工具，不再暴露市场数据工具。 |

## 工具代码
`AlphaVantageGlobalQuoteTool` 继承 `FlowToolCall`：

```python
class AlphaVantageGlobalQuoteTool(FlowToolCall):
    @property
    def name(self) -> str:
        return "alpha_vantage_global_quote"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return dict(GlobalQuoteInput.model_json_schema())

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> dict[str, Any]:
        ...
```

这个工具在 Python runtime 中发起 HTTPS 请求，并把结构化 dict 返回给 session loop。loop 会把返回值序列化为 `tool_result` chunk，供 analyst 的后续模型轮次使用。

公开运行时需要用户显式设置自己的 Alpha Vantage key。这个 key 只用于演示外部数据工具，不属于 OpenRath runtime 的核心能力。

## 运行
从仓库根目录运行：

```bash
export ALPHA_VANTAGE_API_KEY=...
python example/trading_agents/main.py \
  --ticker NVDA \
  --as-of 2026-05-11 \
  --workdir .workspace/trading-agents
```

该例子还需要真实 OpenAI-compatible LLM 配置：

```bash
export OPENAI_API_KEY=...
export OPENAI_BASE_URL=...
export OPENAI_DEFAULT_MODEL=...
```

真实 key 应保存在环境变量、本地 `.env` 或密钥管理系统中，不写入脚本、文档或提交记录。

## 观察结果
| 位置 | 看什么 |
| --- | --- |
| stdout | 最终输出 session，包含各角色追加的 assistant rows。 |
| workspace | analyst、researcher、trader、risk PM 相关报告文件。 |
| session chunks | analyst 的 tool call、tool result，以及后续角色如何沿用同一 session。 |
| workflow repr | 直接登记的五个 `AgentParam`。 |

## 常见问题
| 现象 | 检查方向 |
| --- | --- |
| `ALPHA_VANTAGE_API_KEY is required` | 显式设置 `ALPHA_VANTAGE_API_KEY`。 |
| Alpha Vantage rate limit | 换 ticker 或等待额度恢复。 |
| LLM 请求失败 | 检查模型网关配置。 |
| 后续角色没有参考 analyst 结果 | 打印 chunk table，确认 analyst 是否产生了 tool result 和报告内容。 |
| workspace 没有报告文件 | 检查模型是否实际调用了写文件工具。 |

## 练习
1. 只保留 analyst 和 risk PM 两个阶段，观察输出差异。
2. 把 `AlphaVantageGlobalQuoteTool` 改成支持多个 ticker。
3. 给 trader 阶段单独传入一个自定义风险计算工具。
