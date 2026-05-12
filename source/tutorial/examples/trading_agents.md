# 交易研究示例（Trading Agents）

对应目录：`example/trading_agents/`。

这个例子展示一个 TradingAgents-style 的顺序多角色 workflow。它使用真实 LLM 配置，并把 Alpha Vantage quote API 包装成 `FlowToolCall`，让 analyst agent 先调用市场数据工具，再把同一个 `Session` 交给后续角色继续处理。

## 结构（Structure）

| 文件 | 负责内容 |
| --- | --- |
| `agents.py` | 定义 analyst、bear researcher、bull researcher、trader、risk/PM 的 system prompts。 |
| `tools.py` | 定义 `AlphaVantageGlobalQuoteTool`，通过 `FlowToolCall` 暴露 `alpha_vantage_global_quote`。 |
| `workflow.py` | 定义 `TradingAgentsWorkflow`，按顺序运行五个 agent。 |
| `_env.py` | 加载 OpenAI-compatible LLM 配置，并检查 Alpha Vantage 配置。 |
| `main.py` | CLI 入口，构造 user session、绑定 local backend、运行 workflow。 |

## Agent 顺序（Agent Order）

| 顺序 | Agent | 行为 |
| --- | --- | --- |
| 1 | analyst | 调用 `alpha_vantage_global_quote`，写入 `analyst_report.md`。 |
| 2 | researcher_bear | 基于已有 session 提出 bearish risks，写入 `researcher_bear_report.md`。 |
| 3 | researcher_bull | 回应 bear case，写入 `researcher_bull_report.md`。 |
| 4 | trader | 输出 action / size / timeline JSON，写入 `trader_report.md`。 |
| 5 | risk_pm | 审核 trader proposal，写入 `risk_pm_report.md`。 |

每一步都调用 `run_session_loop(...)`。输出 `Session` 会继续交给下一步，因此后续角色可以读取前面角色留下的 assistant chunks、tool results 和文件写入意图。

## Workflow 代码（Workflow Code）

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
        s = run_session_loop(s, self.researcher_bear.agent_session, agent_provider=self.researcher_bear.provider)
        s = run_session_loop(s, self.researcher_bull.agent_session, agent_provider=self.researcher_bull.provider)
        s = run_session_loop(s, self.trader.agent_session, agent_provider=self.trader.provider)
        return run_session_loop(s, self.risk_pm.agent_session, agent_provider=self.risk_pm.provider)
```

## 工具代码（Tool Code）

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

## 运行（Run）

从仓库根目录运行：

```bash
python example/trading_agents/main.py \
  --ticker NVDA \
  --as-of 2026-05-11 \
  --workdir .workspace/trading-agents
```

该例子需要真实 OpenAI-compatible LLM 配置。市场数据工具读取 Alpha Vantage 配置；如需稳定运行，应显式设置：

```bash
export ALPHA_VANTAGE_API_KEY=...
```

## 检查结果（What To Inspect）

运行后重点看三类东西：

| 位置 | 看什么 |
| --- | --- |
| stdout | 最终输出 session，包含各角色追加的 assistant rows。 |
| workspace | `analyst_report.md`、`trader_report.md`、`risk_pm_report.md` 等文件。 |
| session chunks | analyst 的 tool call、tool result，以及后续角色如何沿用同一 session。 |

这个例子适合展示 OpenRath 的 multi-agent 组合方式：agent 只是 `AgentParam`，workflow 决定执行顺序，session 承载跨角色上下文。
