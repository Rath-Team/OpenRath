(openrath-documentation)=
# OpenRath

<div class="or-home-hero">
  <p class="or-slogan">An open-source, PyTorch-like API framework for dynamic multi-agent workflows.</p>
  <p>OpenRath treats the session as the primary carrier through an agent run: Session holds the evolving chunk table, Backend controls where tools execute, and Workflow composes agents into reusable pipelines.</p>
  <p class="or-cta">
    <a class="or-button or-button-primary" href="tutorial/index.html">Start Tutorials</a>
    <a class="or-button" href="developer_notes/index.html">Read Developer Notes</a>
    <a class="or-button or-button-muted" href="https://github.com/Rath-Team/OpenRath">GitHub</a>
  </p>
</div>

```python
import os

from rath import flow
from rath.llm import Provider
from rath.session import Session

agent = flow.Agent(
    system_prompt="Use tools when helpful.",
    provider=Provider(
        base_url=os.environ.get("OPENAI_BASE_URL"),
        api_key=os.environ["OPENAI_API_KEY"],
        model=os.environ["OPENAI_DEFAULT_MODEL"],
    ),
)

user = Session.from_user_message(
    "Create a file, then read it back."
).to("local", spec="./")

out = agent(user)
```

Tutorials use scripted LLM responses where reproducibility matters. Production
agent workflows use the same `Session`, `FlowToolCall`, `Workflow`, and
`Backend` abstractions with an OpenAI-compatible `Provider`.

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
| `Session` | Carries ordered chunk rows, sandbox placement, and lineage metadata through a run. |
| `Backend` | Opens the local or OpenSandbox execution environment attached to a session. |
| `FlowToolCall` | Exposes JSON schemas to the model and Python callables to the runtime. |
| `Workflow` | Composes agents and session transformations as ordinary Python modules. |
| `AgentParam` | Stores the agent system session plus LLM routing options. |
| `Provider` | Stores OpenAI-compatible chat completion identity and request parameters. |

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
