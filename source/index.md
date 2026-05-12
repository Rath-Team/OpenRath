(openrath-documentation)=
# OpenRath

<div class="or-home-hero">
  <p class="or-slogan">A opensource, torch-like api framework for dynamic multi-agent workflow.</p>
  <p>OpenRath brings PyTorch-style composability to agent workflows: use Session for state, FlowToolCall for callable tool capabilities, and Backend for controlled execution placement.</p>
  <p class="or-cta">
    <a class="or-button or-button-primary" href="tutorial/index.html">Start Tutorials</a>
    <a class="or-button" href="developer_notes/index.html">Read Developer Notes</a>
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

Tutorials use scripted LLM responses where reproducibility matters. Production
agent workflows use the same `Session`, `FlowToolCall`, `Workflow`, and
`Backend` abstractions with a configured model provider.

## Where To Start

| Path | Use it for | Entry |
| --- | --- | --- |
| Installation | Install OpenRath, configure model credentials, and connect a sandbox backend when needed. | [Installation](install.md) |
| Tutorials | Learn from runnable code, then adapt examples including multi-agent workflows. | [Tutorials](tutorial/index.md) |
| Developer Notes | Understand runtime components, call boundaries, and how the docs map to source code. | [Developer Notes](developer_notes/index.md) |
| API Reference | Look up public modules, function signatures, and integration points. | [API Reference](reference/index.md) |

## Core Model

| Concept | Role |
| --- | --- |
| `Session` | Carries conversation tables, backend placement, and lineage metadata. |
| `FlowToolCall` | Exposes JSON schemas to the model and Python callables to the runtime. |
| `Backend` | Opens sandboxes and executes command, file, and code payloads. |
| `Workflow` | Composes agent behavior and session transformations as ordinary Python modules. |
| `Provider` | Stores OpenAI-compatible chat completion model and request parameters. |

## Runnable Workflows

| Example | Demonstrates |
| --- | --- |
| [Trading Agents](tutorial/examples/trading_agents.md) | A sequential research workflow with analyst, bear/bull researchers, trader, risk, and PM roles. |
| [Engineering Agents](tutorial/examples/engineering_agents.md) | A nested engineering workflow with lead, feature squad, backend pair, frontend, and QA roles. |
| [Research Transformer](tutorial/examples/research_transformer.md) | An academic writing pipeline with branch workflows, repeated layers, compression, and optional image tooling. |

## PyTorch Mental Model

| PyTorch mental model | OpenRath counterpart |
| --- | --- |
| Tensor carries data | `Session` carries agent state |
| Module composes computation | `Workflow` / `Agent` composes behavior |
| device controls placement | `Backend` controls execution placement |
| callable module exposes a reusable interface | `FlowToolCall` exposes tools |

```{toctree}
---
maxdepth: 3
caption: OpenRath
hidden:
---

Installation <install>
Tutorials <tutorial/index>
Developer Notes <developer_notes/index>
API Reference <reference/index>
```
