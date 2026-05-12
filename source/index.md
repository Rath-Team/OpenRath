(openrath-documentation)=
# OpenRath

<div class="or-home-hero">
  <h2>A PyTorch-inspired runtime for LLM agent workflows</h2>
  <p>OpenRath brings PyTorch-style composability to agents: explicit sessions for state, structured tools for callable capabilities, and backends for controlled execution.</p>
  <p class="or-cta">
    <a class="or-button or-button-primary" href="tutorial/index.html">Start with Tutorials</a>
    <a class="or-button" href="developer_notes/index.html">Developer Notes</a>
    <a class="or-button or-button-muted" href="https://github.com/Rath-Team/OpenRath">GitHub</a>
  </p>
</div>

```python
from rath import flow
from rath.session import Session

agent = flow.Agent(
    system_prompt="Use tools when helpful.",
    model="gpt-5.5",
)

user = Session.from_user_message(
    "Create a file, then read it back."
).to("local")

out = agent(user)
```

The tutorials use scripted LLM responses for deterministic runs. Real agents use the same `Session`, `FlowToolCall`, `Workflow`, and `Backend` abstractions with your configured model provider.

## Where To Start

| Path | Use it for | Start here |
| --- | --- | --- |
| Install | Set up OpenRath, LLM credentials, and optional sandbox backends. | [Install](install.md) |
| Tutorials | Learn from runnable code, then adapt full examples, including multi-agent workflows. | [Tutorials](tutorial/index.md) |
| Developer Notes | Understand the core runtime components and their boundaries. | [Developer Notes](developer_notes/index.md) |
| API Reference | Look up public modules, signatures, and integration points. | [API Reference](reference/index.md) |

## Core Model

| Concept | Role |
| --- | --- |
| `Session` | Carries chunk transcript, backend placement, and lineage metadata. |
| `FlowToolCall` | Exposes a JSON schema to the model and a Python callable to the runtime. |
| `Backend` | Opens sandboxes and executes command, file, and code payloads. |
| `Workflow` | Composes agents and session transformations as Python modules. |
| `Provider` | Stores model and request options for OpenAI-compatible chat completions. |

## Runnable Workflows

| Example | What it shows |
| --- | --- |
| [Trading Agents](tutorial/examples/trading_agents.md) | A sequential research workflow: analyst, bear/bull researchers, trader, and risk/PM. |
| [Engineering Agents](tutorial/examples/engineering_agents.md) | A nested engineering workflow: lead, feature squad, backend pair, frontend, and QA. |

## PyTorch Mental Model

| PyTorch | OpenRath |
| --- | --- |
| Tensor carries data | `Session` carries agent state |
| Module composes computation | `Workflow` / `Agent` composes behavior |
| device controls placement | `Backend` controls execution placement |
| callable modules expose reusable interfaces | `FlowToolCall` exposes tools |

```{toctree}
---
maxdepth: 3
caption: OpenRath
hidden:
---

install
tutorial/index
developer_notes/index
reference/index
```
