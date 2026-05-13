# AgentParam
`AgentParam` stores an agent's system context and model request options. A workflow can register agent configuration the same way it registers child modules; execution is still handled by `Session` and `run_session_loop(...)`.

This page explains where an agent's system prompt is stored, how model parameters enter requests, what `flow.Agent` wraps, and why the loop returns a user session.

## Overview
In OpenRath, an agent identity has two parts:

| Part | Current implementation | Purpose |
| --- | --- | --- |
| System context | `agent_session` | Stores the system prompt, which appears at the start of the LLM request. |
| Model options | `provider` | Stores OpenAI-compatible request options such as model, temperature, and tool choice. |

`AgentParam` itself only maintains these two values. It can be auto-registered, printed, and enumerated by `Workflow`; model calls, tool execution, sandbox transfer, and session graph writeback happen in `run_session_loop(...)`.

This boundary defines the split between three objects: `AgentParam` describes the agent identity, `Session` describes the current task state, and `Workflow.forward(...)` describes execution order.

## Source map
| File | Responsibility |
| --- | --- |
| `src/rath/flow/agent_param.py` | `AgentParam` dataclass, read-only `data` view, repr. |
| `src/rath/flow/agent.py` | `Agent` preset workflow that creates `AgentParam` and calls the loop. |
| `src/rath/llm/provider.py` | `Provider`, which stores model and sampling parameters. |
| `src/rath/session/loop.py` | Combines agent session and user session into a request, then returns a new user session. |
| `src/rath/flow/workflow.py` | Registers `AgentParam` during attribute assignment. |

## Data Structure
`AgentParam` is currently a slots dataclass with two fields:

```python
from rath.flow import AgentParam, Provider
from rath.session import Session

param = AgentParam(
    agent_session=Session.from_agent_prompt("You are concise."),
    provider=Provider(api_key="sk-...", model="gpt-5.5"),
)
```

| Field | Type | Typical source | Runtime meaning |
| --- | --- | --- | --- |
| `agent_session` | `Session` | `Session.from_agent_prompt(...)` | System context placed at the start of the request. |
| `provider` | `Provider` | `Provider(model=...)` | Model configuration passed to the LLM request builder. |

`param.data` returns a `MappingProxyType` containing `agent_session` and `provider`. Callers can read this mapping, but cannot mutate the underlying fields through it.

## Why The System Prompt Is A Session
`Session.from_agent_prompt(...)` creates a session containing only a system chunk. This has three direct benefits:

| Benefit | Corresponding behavior |
| --- | --- |
| Unified request assembly | system, user, assistant, and tool result chunks all become LLM messages through `chunk_table_to_messages(...)`. |
| Traceable lineage | `run_session_loop(...)` records both the user session and agent session as parents of the output session. |
| Agent reuse | The same `agent_session` can be combined with different user sessions, while output still returns only user-side results. |

In the actual request, the loop reads `agent_session.chunk_table`, then `user_session.chunk_table`, then builds the model request:

```text
request messages
  system rows from agent_session
  user / assistant / tool rows from user_session
```

The output session starts from user-side rows, then appends new assistant rows and tool result rows. The agent's system rows participate in the request but are not copied into the output session.

## How Provider Enters The Request
`Provider` stores optional parameters for OpenAI-compatible chat completions. Current fields include `model`, `temperature`, `top_p`, `max_tokens`, `tool_choice`, `parallel_tool_calls`, `response_format`, `reasoning_effort`, `verbosity`, and `extra_create_args`.

`run_session_loop(...)` passes `Provider` to `provider_into_chat_request(...)`:

```python
from rath.session import run_session_loop

out = run_session_loop(
    user_session=user,
    agent_session=param.agent_session,
    agent_provider=param.provider,
)
```

The request `messages` and `tools` are built by the loop from the session and tool table; model, sampling, tool choice, and related options come from `Provider`. This keeps agent configuration separate from the current task context.

## Registration In Workflow
Assigning `AgentParam` to a `Workflow` attribute puts it into `_agents` through `Workflow.__setattr__`:

```python
from rath.flow import AgentParam, Provider, Workflow
from rath.session import Session


class ReviewerWorkflow(Workflow):
    def __init__(self):
        super().__init__()
        self.reviewer = AgentParam(
            Session.from_agent_prompt("Review the implementation."),
            Provider(api_key="sk-...", model="gpt-5.5"),
        )
```

This affects two developer-facing behaviors:

| Behavior | Notes |
| --- | --- |
| `named_agents()` | Returns agent params registered through attribute assignment. |
| `repr(workflow)` | Prints registered agents in a form similar to a PyTorch module tree. |

Registration only applies to `AgentParam`. Normal fields, tool lists, executors, and child workflows remain plain Python attributes.

## What `flow.Agent` Wraps
`flow.Agent` is the common single-agent workflow. On initialization it creates one `AgentParam` and stores a list of tool instances:

```python
from rath import flow
from rath.llm import Provider

agent = flow.Agent(
    system_prompt="Use tools when useful.",
    provider=Provider(api_key="sk-...", model="gpt-5.5"),
)

out = agent(user)
```

Internal structure:

```text
flow.Agent.__init__
  Session.from_agent_prompt(system_prompt)
  AgentParam(agent_session, provider)
  tools list

flow.Agent.forward
  run_session_loop(user_session, agent_session, agent_provider, tools)
```

`register_tool(tool)` deduplicates by tool name and returns directly if the name already exists. `unregister_tool(name)` filters out tools with that name. Tools are exposed to the model when `run_session_loop(...)` merges the tool table.

## When To Use AgentParam Directly
Single-agent calls usually use `flow.Agent`. Multi-agent workflows usually use `AgentParam` directly and expand the execution order step by step in `forward(...)`:

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

Here, `planner` and `writer` each have their own system prompt. The second loop receives the first loop's output session, so the planner's assistant content becomes input context for the writer.

## Output Session Boundary
`run_session_loop(...)` returns a new session that inherits user-side history and appends newly produced model content. It also moves the sandbox handle from the input session to the output session.

| Input | Participates in request | Appears in output session |
| --- | --- | --- |
| `agent_session` | Yes | No |
| `user_session` | Yes | Yes |
| assistant response | Newly produced | Yes |
| tool result | Produced when tools are called | Yes |
| sandbox handle | Provided by user session | Moved to output session |

The agent's system prompt does not pollute user-side context. When a workflow calls multiple agents in sequence, the user session moves across roles, while each agent's system prompt applies only to that agent's request.

## Current Boundaries
| Behavior | Current implementation |
| --- | --- |
| field count | `AgentParam` only has `agent_session` and `provider`. |
| memory | There is no separate memory field yet; long-term memory can be represented by workflow state or session content for now. |
| execution capability | `AgentParam` has no `forward(...)`; execution is handled by `Workflow`, `Agent`, or `run_session_loop(...)`. |
| `data` | Returns a read-only mapping, but does not deep-copy values. |
| provider sharing | Multiple `AgentParam` values can share the same `Provider` instance. |
| system prompt | Usually created through `Session.from_agent_prompt(...)`. |

## Code Reading Checkpoints
1. In `agent_param.py`, check the `AgentParam` fields and `data` behavior.
2. In `workflow.py`, check how `__setattr__` registers `AgentParam`.
3. In `agent.py`, check how `flow.Agent` creates `AgentParam` from `system_prompt` and `model`.
4. In `loop.py`, check the request assembly order with `head = chunk_table_to_messages(agent_session.chunk_table)` and `tail = chunk_table_to_messages(...)`.
5. In `loop.py`, check how the output session sets `parent_session_ids=(user_session.id, agent_session.id)`.

## Test Coverage
| Behavior | Tests |
| --- | --- |
| import contract | `tests/test_import.py` |
| workflow agent registration and loop | `tests/flow/test_workflow_agent.py` |
| custom tool through agent/loop | `tests/flow/test_flow_tool_user_subclass.py` |
