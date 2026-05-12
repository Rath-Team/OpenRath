# Trading Agents

Directory: `example/trading_agents/`.

Trading Agents demonstrates a research chain: the analyst first fetches an Alpha Vantage quote through a `FlowToolCall`, the bear and bull researchers form separate views, and the trader and risk PM continue working along the same `Session`.

## What it covers
| Topic | Result |
| --- | --- |
| sequential multi-agent | Five roles process the same session in a fixed order. |
| agent identity | Each role is an `AgentParam` with its own system prompt. |
| external data tool | Only the analyst stage receives `AlphaVantageGlobalQuoteTool`. |
| session continuity | Later roles read the assistant rows and tool results left by earlier roles. |
| session-level parallel | After the analyst output, the workflow can fork bear and bull research branches. |
| workspace output | Each role is prompted to write its own report file. |

## Directory structure
| File | Responsibility |
| --- | --- |
| `agents.py` | Defines system prompts for the analyst, bear researcher, bull researcher, trader, and risk PM. |
| `tools.py` | Defines `AlphaVantageGlobalQuoteTool` and exposes `alpha_vantage_global_quote`. |
| `workflow.py` | Defines `TradingAgentsWorkflow`, which runs the five agents in order. |
| `_env.py` | Loads OpenAI-compatible LLM configuration and requires an explicit Alpha Vantage key. |
| `main.py` | CLI entry point that constructs the user session, binds the local backend, and runs the workflow. |

## Agent order
| Order | Agent | Behavior |
| --- | --- | --- |
| 1 | analyst | Calls `alpha_vantage_global_quote` and produces market data plus initial analysis. |
| 2 | researcher_bear | Uses the existing session to develop risks and bearish arguments. |
| 3 | researcher_bull | Uses the same session to develop bullish arguments. |
| 4 | trader | Combines the research and produces a trading proposal. |
| 5 | risk_pm | Reviews the trader proposal and gives risk-control guidance. |

Each step calls `run_session_loop(...)`. The output `Session` is passed to the next step, so later roles can read assistant chunks, tool results, and file-writing intent from earlier roles.

## Session-level parallelism
For readability, the current example runs the bear researcher and bull researcher sequentially. A real workflow can fork two sessions after the analyst stage and let the researchers run in parallel:

```python
from concurrent.futures import ThreadPoolExecutor
from rath.session import ChunkKind, Session


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

The parallel unit here is the `Session`. `fork()` copies the transcript and backend target produced by the analyst stage, but it does not copy an already-open sandbox handle. The two researcher branches produce independent lineages; the workflow must explicitly decide how the trader stage aggregates them.

One minimal aggregation approach is to extract the final assistant message from each branch, then build a new user session for the trader:

```python
def last_assistant_text(s: Session) -> str:
    for row in reversed(s.chunk_table.rows):
        if row.kind == ChunkKind.ASSISTANT and row.payload.get("content"):
            return str(row.payload["content"])
    return ""


trader_input = Session.from_user_message(
    "Compare the two research branches and produce one trading proposal.\n\n"
    f"Bear branch:\n{last_assistant_text(bear_session)}\n\n"
    f"Bull branch:\n{last_assistant_text(bull_session)}"
).to("local")

trader_session = run_session_loop(
    trader_input,
    self.trader.agent_session,
    agent_provider=self.trader.provider,
    tools=None,
)
```

If both branches write report files, assign different workspaces to the branches. A direct `fork()` copies the original session backend target; when the original session is bound with `spec="."`, both branches may write into the same directory.

```python
bear_input = analyst_session.fork().to("local", spec=".workspace/trading-bear")
bull_input = analyst_session.fork().to("local", spec=".workspace/trading-bull")
```

## Workflow code
The core structure comes from `example/trading_agents/workflow.py`:

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

Key points:

| Line | Explanation |
| --- | --- |
| `prov = Provider(model=model)` | All five roles share the same model configuration. |
| `self.analyst = AgentParam(...)` | Assignment registers the agent with the `Workflow`. |
| `market_tools = [AlphaVantageGlobalQuoteTool()]` | The market data tool is passed only to the analyst. |
| `s = run_session_loop(s, ...)` | Each role receives the output session from the previous role. |
| `tools=None` | Later roles use built-in tools and no longer receive the market data tool. |

## Tool code
`AlphaVantageGlobalQuoteTool` inherits from `FlowToolCall`:

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

This tool sends the HTTPS request in the Python runtime and returns a structured dict to the session loop. The loop serializes the return value into a `tool_result` chunk for later analyst model turns.

Public runs require users to set their own Alpha Vantage key explicitly. This key is only used to demonstrate an external data tool; it is not part of the core OpenRath runtime.

## Run
Run from the repository root:

```bash
export ALPHA_VANTAGE_API_KEY=...
python example/trading_agents/main.py \
  --ticker NVDA \
  --as-of 2026-05-11 \
  --workdir .workspace/trading-agents
```

This example also needs a real OpenAI-compatible LLM configuration:

```bash
export OPENAI_API_KEY=...
export OPENAI_BASE_URL=...
export OPENAI_DEFAULT_MODEL=...
```

Store real keys in environment variables, a local `.env`, or a secrets manager, not in scripts, docs, or commit history.

## Successful output
The script prints the final `Session(...)`. On success, the session shows the analyst's market data tool call and assistant rows appended by later roles:

```text
Session(
  chunks=[
    [0] user: 'Ticker: NVDA...'
    [1] assistant: tools=[alpha_vantage_global_quote(...)]
    [2] tool_result: name='alpha_vantage_global_quote', body='{"symbol": "NVDA", ...}'
    [3] assistant: text='Analyst report...'
    [4] assistant: text='Bear researcher...'
    [5] assistant: text='Bull researcher...'
    [6] assistant: text='Trader proposal...'
    [7] assistant: text='Risk PM review...'
  ]
)
```

If the model calls file-writing tools, reports from each role also appear under `.workspace/trading-agents`. File names and contents depend on the prompt and model behavior.

## What to inspect
| Location | What to check |
| --- | --- |
| stdout | The final output session, including assistant rows appended by each role. |
| workspace | Report files related to the analyst, researchers, trader, and risk PM. |
| session chunks | The analyst tool call and tool result, plus how later roles continue the same session. |
| workflow repr | The five directly registered `AgentParam` instances. |

## Troubleshooting
| Symptom | Check |
| --- | --- |
| `ALPHA_VANTAGE_API_KEY is required` | Set `ALPHA_VANTAGE_API_KEY` explicitly. |
| Alpha Vantage rate limit | Change the ticker or wait for quota recovery. |
| LLM request fails | Check the model gateway configuration. |
| Later roles do not reference analyst results | Print the chunk table and confirm that the analyst produced a tool result and report content. |
| Workspace has no report files | Check whether the model actually called file-writing tools. |

## Exercises
1. Keep only the analyst and risk PM stages, then observe how the output changes.
2. Modify `AlphaVantageGlobalQuoteTool` to support multiple tickers.
3. Pass a custom risk calculation tool only to the trader stage.
