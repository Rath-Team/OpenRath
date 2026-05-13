# Workflow
`Workflow` is OpenRath's composition layer. It organizes one or more agent configurations into a callable object and expresses runtime logic as `Session -> Session`.

This page explains the structure from single-agent to multi-agent workflows, `AgentParam` registration rules, nested workflow composition, and how session, sandbox, and tool traces move through the call chain.

The diagram below shows the intended mental model: a workflow is a callable
module over `Session`, and its internal agents can fork, compose, and compress
state explicitly.

```{figure} ../_static/core-workflow.png
:alt: Workflow composition overview

`Workflow.forward(session) -> Session` keeps orchestration in ordinary Python
while preserving session graph and sandbox traceability.
```

## Overview
OpenRath workflows follow a pattern close to PyTorch modules:

| PyTorch intuition | OpenRath equivalent |
| --- | --- |
| `Module.forward(x)` defines computation | `Workflow.forward(session)` defines agent orchestration |
| Child modules are attached as attributes | `AgentParam` is registered by attribute assignment |
| Tensors move between modules | `Session` moves between agents and workflows |
| Module tree can be printed | `repr(workflow)` prints registered agents |

`Workflow` has a small job: collect directly attached `AgentParam` values, provide the `forward(...)` convention, and make instances callable through `workflow(session)`. Execution order, branching, compression, tool injection, and child workflow calls are written explicitly in normal Python code.

## Source map
| File | Responsibility |
| --- | --- |
| `src/rath/flow/workflow.py` | `Workflow` base class, attribute registration, `named_agents()`, repr. |
| `src/rath/flow/agent_param.py` | `AgentParam` values that can be registered by a workflow. |
| `src/rath/flow/agent.py` | `Agent` preset workflow wrapping one agent loop. |
| `src/rath/flow/compressor.py` | `Compressor` preset workflow wrapping compression. |
| `src/rath/session/loop.py` | Runs the LLM loop, tool calls, sandbox transfer, and lineage writeback. |
| `example/trading_agents/workflow.py` | Sequential multi-agent workflow example. |
| `example/engineering_agents/workflows.py` | Nested workflow example. |

## Minimal Workflow
Inherit from `Workflow` and implement `forward(self, session) -> Session`:

```python
from rath.flow import Workflow
from rath.session import Session


class IdentityWorkflow(Workflow):
    def forward(self, session: Session) -> Session:
        return session
```

`Workflow.__call__(session)` directly calls `forward(session)`. The base `forward(...)` raises `NotImplementedError`, so subclasses must define their own runtime logic.

## AgentParam Auto-Registration
When an `AgentParam` is assigned as a workflow attribute, `Workflow.__setattr__` records it in `_agents`:

```python
from rath.flow import AgentParam, Provider, Workflow
from rath.session import Session


class PlanningWorkflow(Workflow):
    def __init__(self):
        super().__init__()
        self.planner = AgentParam(
            Session.from_agent_prompt("Plan the work."),
            Provider(api_key="sk-...", model="gpt-5.5"),
        )
```

That assignment has two effects:

| Result | Behavior |
| --- | --- |
| Python attribute | Usable through `self.planner`. |
| workflow registry | Visible through `named_agents()` and `repr(workflow)`. |

`named_agents()` returns a tuple sorted by attribute name. When an attribute is deleted, `Workflow.__delattr__` removes the matching registered item from `_agents`.

## Single-Agent To Multi-Agent
The smallest runnable path can use the preset `flow.Agent` directly:

```python
from rath import flow
from rath.llm import Provider

agent = flow.Agent(
    system_prompt="Answer clearly.",
    provider=Provider(api_key="sk-...", model="gpt-5.5"),
)

out = agent(user_session)
```

For multiple roles, define each role as an `AgentParam` and call `run_session_loop(...)` step by step in `forward(...)`:

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

The first loop output becomes the second loop input. The session graph records the parents for each loop, and the sandbox handle moves from input session to output session.

## Session Is The Composition Unit
`Workflow` instances communicate through `Session`. That keeps several composition patterns consistent:

| Pattern | Code shape | Use case |
| --- | --- | --- |
| Sequential call | `s = step_a(s); s = step_b(s)` | Roles work in a fixed order. |
| Branching exploration | `left = s.fork(); right = s.fork()` | Derive multiple candidate paths from the same context. |
| Session-level parallelism | `left = pool.submit(...); right = pool.submit(...)` | Send multiple forked sessions to different agents at the same time. |
| Detach from history | `clean = s.detach()` | Reuse content while cutting lineage. |
| Compress context | `compressor(s)` | Shorten history before the next stage. |
| Nested workflow | `s = self.child.forward(s)` | Split complex flows into smaller modules. |

All of these operations still revolve around the session graph. `fork()`, `detach()`, `run_session_loop(...)`, and `run_session_compress(...)` write lineage to output sessions; tool results remain as chunks in the session table; sandbox lifecycle is owned and transferred by the session.

## Session-Level Parallelism
OpenRath multi-agent parallelism is based on session branches, not a special scheduling DSL. After an upstream agent produces a session, use `fork()` to derive branches, then use normal Python concurrency tools to send those branches to different agents.

```python
from concurrent.futures import ThreadPoolExecutor
from rath.session import ChunkKind, Session


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

    def last_assistant_text(s: Session) -> str:
        for row in reversed(s.chunk_table.rows):
            if row.kind == ChunkKind.ASSISTANT and row.payload.get("content"):
                return str(row.payload["content"])
        return ""

    trader_input = Session.from_user_message(
        "Combine the two research branches.\n\n"
        f"Bear branch:\n{last_assistant_text(bear_session)}\n\n"
        f"Bull branch:\n{last_assistant_text(bull_session)}"
    ).to("local")

    return run_session_loop(
        trader_input,
        self.trader.agent_session,
        agent_provider=self.trader.provider,
        tools=None,
    )
```

This pattern has three boundaries:

| Boundary | Notes |
| --- | --- |
| lineage | Both forked sessions keep the same parent, and later loop outputs record their own agent parent. |
| sandbox | `fork()` copies the backend target but not the open handle; parallel branches open their own sandbox handles as needed. |
| aggregation | There is no built-in merge primitive yet; the workflow must decide explicitly how to summarize multiple output sessions into the next input. The example above builds the trader input from the last assistant text in each branch. |

OpenRath's parallel unit is therefore the session. Tool stream concurrency belongs to the backend layer, and `Provider.parallel_tool_calls` belongs to LLM tool-call parameters; both are separate from session-level parallelism.

If branches write to the workspace, assign different directories explicitly. `fork()` copies the backend target; when the source session uses `spec="."`, both forked branches may still target the same host directory. A safer pattern is to reset a branch-specific workspace after fork:

```python
auth_input = session.fork().to("local", spec=".workspace/auth-branch")
data_input = session.fork().to("local", spec=".workspace/data-branch")
```

OpenSandbox follows the same rule: each branch can own an independent sandbox handle, but the host bind path still comes from `spec` and the server allowlist.

## Preset Workflows
OpenRath currently provides two preset subclasses:

| Class | Wraps | Best for |
| --- | --- | --- |
| `Agent` | One `AgentParam`, one tools list, one `run_session_loop(...)` | Single-agent calls and quick tool integration. |
| `Compressor` | One `AgentParam`, one `run_session_compress(...)` | Compressing a long session into a new user-side session. |

`Agent.register_tool(...)` deduplicates by tool name. `Compressor` asks the model to produce a new user message; the compressed result keeps session lineage and continues to hold the input session's sandbox configuration and handle.

## Nested Workflow
The Engineering Agents example in the repository shows nested workflows:

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

The current base class registers only directly assigned `AgentParam` values. `self._squad` and `self._qa` are normal Python attributes, and `forward(...)` calls them explicitly. The outer workflow's `repr(...)` shows only directly registered agents; nested composition is visible through source structure and the call path.

## Trading Agents Example
`example/trading_agents/workflow.py` shows a fixed-order multi-role flow:

```text
analyst
  researcher_bear
  researcher_bull
  trader
  risk_pm
```

The `analyst` stage injects `AlphaVantageGlobalQuoteTool`; later stages read the tool result and assistant content already stored in the session. External data tools can be given to a single role, and their results pass to later roles through the session.

The external market API is only for demonstrating tool capability. Public examples require users to set their own API key explicitly so a default key is not mistaken for a product capability.

## Engineering Agents Example
`example/engineering_agents/workflows.py` shows hierarchical composition:

| Level | Workflow | Execution |
| --- | --- | --- |
| L1 | `EngineeringProjectWorkflow` | lead plan -> feature squad -> QA. |
| L2 | `FeatureSquadWorkflow` | architect -> backend pair -> frontend. |
| L3 | `BackendPairWorkflow` | backend auth -> backend data. |
| QA | `QualityAssuranceWorkflow` | Tests and risk checks based on the full session. |

The example shows how to organize complex engineering work: each workflow owns its local sequence, the parent workflow chains child workflows, and all stages share the same session-passing chain.

## Tool And Sandbox Boundaries
Inside a workflow, tools and sandbox still take effect through `run_session_loop(...)`:

| Item | Where it happens |
| --- | --- |
| Tool list merge | At the start of each `run_session_loop(...)`. |
| Tool call record | Written to the output session as a `tool_result` chunk. |
| sandbox handle | Taken from the input session with `take_sandbox()`, then bound to the output session. |
| sandbox backend spec | Stored on the output session. |
| lineage | Output session records both the user session and agent session as parents. |

A workflow can therefore give different roles different tools; the same sandbox can move through multiple roles with the session; later agents can see results produced by earlier tools.

## Call Path
```text
workflow(session)
  Workflow.__call__
  subclass.forward(session)
  run_session_loop or child workflow
  returned Session carries new chunks, sandbox, lineage
```

When using the preset `Agent`:

```text
flow.Agent.forward(session)
  run_session_loop(
    user_session=session,
    agent_session=self.agent.agent_session,
    agent_provider=self.agent.provider,
    tools=self.tools,
  )
```

When using the preset `Compressor`:

```text
flow.Compressor.forward(session)
  run_session_compress(
    user_session=session,
    agent_session=self.agent.agent_session,
    agent_provider=self.agent.provider,
  )
```

## Current Boundaries
| Behavior | Current implementation |
| --- | --- |
| attribute registration | Only attributes assigned to `AgentParam` values enter `_agents`. |
| deletion | `__delattr__` removes the same-named agent from `_agents`. |
| ordering | `named_agents()` sorts by attribute name. |
| base execution | `Workflow.forward(...)` raises `NotImplementedError`. |
| nested workflow | The base class does not automatically register child workflows. |
| async support | `Workflow.forward(...)` is currently synchronous. |
| scheduling policy | Ordering, branching, retries, and concurrency are expressed by the user in Python code. |

## Code Reading Checkpoints
1. In `workflow.py`, check `__slots__ = ("_agents",)` and `__setattr__`.
2. In `workflow.py`, check the sorting rule in `named_agents()`.
3. In `agent.py`, check how `Agent.forward(...)` calls `run_session_loop(...)`.
4. In `compressor.py`, check how the compression workflow calls `run_session_compress(...)`.
5. In `example/trading_agents/workflow.py`, check the fixed-order multi-agent flow.
6. In `example/engineering_agents/workflows.py`, check nested workflows.
7. In `tests/flow/test_workflow_agent.py`, check workflow registration and sandbox transfer tests.

## Test Coverage
| Behavior | Tests |
| --- | --- |
| workflow registration and agent call | `tests/flow/test_workflow_agent.py` |
| import contract | `tests/test_import.py` |
| session compressor live behavior | `tests/integration/test_session_compress_real.py` |

## Related Pages
| Page | Covers |
| --- | --- |
| [AgentParam](agent_param.md) | Agent-side session, provider, and request assembly. |
| [Trading Agents](../tutorial/examples/trading_agents.md) | Sequential multi-role workflow with an external market data tool. |
| [Engineering Agents](../tutorial/examples/engineering_agents.md) | Nested workflow for engineering-team-style agent orchestration. |
