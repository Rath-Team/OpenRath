[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/rath-team-openrath-badge.png)](https://mseep.ai/app/rath-team-openrath)

# OpenRath

<p align="center">
  <img src="assets/readme/logos/openrath-logo-white.png" alt="OpenRath logo" width="860" />
</p>

<p align="center">
  <a href="https://pypi.org/project/openrath/"><img src="https://img.shields.io/pypi/v/openrath.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/openrath/"><img src="https://img.shields.io/pypi/pyversions/openrath.svg" alt="Python"></a>
  <a href="https://github.com/Rath-Team/OpenRath/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-BSD--3--Clause-blue.svg" alt="License"></a>
  <a href="https://docs.openrath.com"><img src="https://img.shields.io/badge/docs-openrath.com-blue" alt="Docs"></a>
  <a href="https://arxiv.org/abs/2606.19409"><img src="https://img.shields.io/badge/arXiv-2606.19409-b31b1b.svg?logo=arxiv&amp;logoColor=white" alt="arXiv"></a>
</p>

<div align="center">

English | [简体中文](README_zh.md)

</div>

---

**OpenRath is a PyTorch-like multi-agent & multi-session framework.**

It turns agent runtime state into explicit, composable Python objects:

- **Session** carries conversation state and inter-agent collaboration lineage.
- **Sandbox** decides where tools actually run.
- **Memory** persists agent memory state across runs.
- **Tool** is the operator-like callable surface exposed to the model.
- **Agent** is a reusable, composable session transformation layer.
- **Workflow** composes multiple agents and workflows into larger systems.
- **Selector** routes between self-describing workflows at runtime, so `if` / `while` control flow stays plain Python.

---

## OpenRath in the PyTorch Lens

<p align="center">
  <img src="assets/readme/diagrams/pytorch-lens.png" alt="OpenRath in the PyTorch Lens" width="860" />
</p>

| PyTorch idea | OpenRath idea | What it means |
| --- | --- | --- |
| `Tensor` | `Session` | The flowing runtime value: ordered chunks, placement, lineage, and usage. |
| `Device` | `Sandbox` / `Backend` | The execution environment where tools run: local process, OpenSandbox, or another backend. |
| `Parameter` | `Memory` | Persistent state bound to an agent or store, recalled and committed across runs. |
| `Function` | `Tool` | A callable operation with model-visible schema and runtime behavior. |
| `nn.Linear` | `Agent` | A reusable layer that maps one session to another using a prompt, provider, tools, and memory. |
| `nn.Module` | `Workflow` | A composable container for agents, tools, session transforms, and nested workflows. |
| control flow | `Selector` | An LLM-backed router that picks the next workflow at runtime, enabling dynamic `if` / `while` over agents. |

Most agent frameworks begin with an agent loop. OpenRath begins with **Session**. That difference matters when one application needs multiple agents, multiple branches, durable memory, sandboxed execution, and traceable lineage at the same time.

OpenRath is designed for this: many agents collaborating across many branchable sessions, while still tracing every role, workspace, memory write, and final output.

<p align="center">
  <img src="assets/readme/diagrams/paradigm-map.png" alt="Multi-Agent Multi-Session Map" width="860" />
</p>

| Paradigm | Typical shape | Example |
| --- | --- | --- |
| Single agent, single session | One model over one conversation | ChatGPT-style chat |
| Multi-agent, single session | Several roles read and write one shared state | Sub-agent-style multi-agent collaboration |
| Single agent, multi-session | One agent manages many session branches | OpenClaw-style session fanout |
| Multi-agent, multi-session | Many agents share many sessions and collaborate or evolve through Session | **OpenRath** |

---

## Why the Multi-Agent-Multi-Session Paradigm

An agent is a transformation layer on Session, so what really needs to be forked, merged, reused, and traced is the Session dataflow—not a separate message history maintained by each agent.

<p align="center">
  <img src="assets/readme/diagrams/multi-agent-multi-session.png" alt="Why Multi-Agent Multi-Session" width="860" />
</p>

OpenRath's design addresses the problems that appear when agent systems move from one assistant to large clusters:

- **Session as the dataflow core.** Context is stored as structured chunks rather than repeatedly copied message strings. Workflows can reuse, fork, compress, and pass context directly, which greatly improves context reuse and reduces token consumption.
- **Session Graph for massive agent clusters.** Large runs need to explain which role, branch, tool call, and workspace produced an answer. Session lineage gives the runtime a graph-shaped provenance layer instead of a pile of post-hoc logs.
- **Session plus Agent Memory.** Short-term session state and long-term memory work together: agents can recall facts before a run and commit new knowledge afterward, so an agent cluster can keep improving as it is used.
- **Modular Workflow.** Managing hundreds or thousands of agents becomes a composition problem instead of prompt spaghetti. Agents are small layers; workflows are nested, reusable, inspectable modules that make large-scale agent management tractable.
- **Sandbox as a backend.** Execution is not hardcoded to one shell. Local, OpenSandbox, or future third-party backends can sit behind the same session placement model, so third-party execution backends plug in flexibly.
- **Memory as a backend.** Recall is not hardcoded to one database. Local memory, OpenViking, or future third-party memory systems can share one memory plane, so third-party memory backends plug in flexibly.

The result is a runtime where state, execution, memory, and orchestration stay decoupled enough to scale, yet remain connected through one flowing value: `Session`.

---

## A Minimal but Complete OpenRath Workflow

```python
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from rath import flow
from rath.flow.tool import FlowToolCall
from rath.session import Session


class WordCountInput(BaseModel):
    text: str = Field(description="Text to count.")


# OpenRath Tool
class WordCountTool(FlowToolCall):
    @property
    def name(self) -> str:
        return "word_count"

    @property
    def description(self) -> str:
        return "Count words in a short text."

    @property
    def parameters(self) -> Mapping[str, Any]:
        return WordCountInput.model_json_schema()

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> dict[str, int]:
        data = WordCountInput.model_validate(dict(arguments))
        return {"words": len(data.text.split())}


# OpenRath Workflow
class ReadmeWorkflow(flow.Workflow):
    def __init__(self) -> None:
        # OpenRath Provider
        provider = flow.Provider(model="gpt-5.5")

        # OpenRath Agent
        self.agent = flow.Agent(
            "Use the `word_count` tool, then answer briefly.",
            provider,
            tools=[WordCountTool()],
            memory="local",
        )

        # OpenRath Compressor
        self.compressor = flow.Compressor(
            "Compress the run into one concise assistant message.",
            provider,
        )

    def forward(self, session: Session) -> Session:
        # OpenRath Memory
        self.agent.remember_memory("The user likes compact technical summaries.")
        session = self.agent(session)
        self.agent.commit_memory(session)
        return self.compressor(session)


workflow = ReadmeWorkflow()

# OpenRath Session
user_session = Session.from_user_message(
    "Count the words in: OpenRath makes agent clusters traceable."
)

# OpenRath Sandbox
user_session = user_session.to("local", spec="./")
out = workflow(user_session)
```

This small program shows the whole shape in a short span: `Session` carries the data, `Sandbox` places execution, `Tool` is registered on an `Agent`, `Memory` persists across runs, `Workflow` composes the path, and `Compressor` shrinks the resulting context.

---

## The Runtime Pieces

### Session — The Flowing State

`Session` is OpenRath's central runtime value. It holds an ordered chunk table containing system, user, assistant, and tool-result rows. It also records sandbox placement, lineage, token usage, and pending lazy work.

This is why OpenRath can model more than a single chat transcript. A session can be forked into a new branch, detached from its parent chain, merged back with another compatible branch, serialized to JSONL, or handed to a different workflow. Agent-side instructions are represented as their own session chunks and prepended by the loop, rather than repeatedly pasted into an opaque prompt.

Common entry points:

- `Session.from_user_message(...)` creates a user-side session.
- `Session.from_agent_prompt(...)` creates an agent/system prompt session.
- `session.to("local", spec="./")` binds a sandbox backend and workspace.
- `session.fork()` creates a traceable branch.
- `session.detach()` creates a new session without parent lineage.
- `session.merge(...)` combines compatible branches and records merge lineage.

### Sandbox — Where Tools Land

Sandbox is the execution placement for a session. It is the OpenRath equivalent of deciding where computation lands. Tools do not run in an abstract prompt; they run against the sandbox currently bound to the session.

```python
session = Session.from_user_message("List files").to("local", spec="./")
```

The `local` backend is always available and runs file, command, and code tools against the host workspace. The optional `opensandbox` backend connects the same tool layer to a containerized OpenSandbox runtime. A returned session keeps the active sandbox ownership, so later tool calls continue from the same execution context instead of silently drifting to another directory or machine.

### Memory — What Survives Between Runs

Memory is a persistent plane parallel to sandbox execution. It is not a tool result and not just prompt text; it is state that can be attached to an agent, recalled before a run, and committed after a run.

The base install includes a zero-dependency local memory backend. It stores data under `.openrath/memory/`, supports lexical BM25 recall without an LLM, and can use embeddings when an embedding provider is configured. OpenViking is available as an optional backend for users who want a richer external memory service.

```python
with flow.Agent("You remember useful facts.", model="gpt-5.5", memory="local") as agent:
    agent.remember_memory("The user works mostly in Python.")
    hits = agent.recall_memory("preferred programming language")
```

Agent memory APIs are intentionally discoverable:

- `memory=` binds a store at construction time.
- `remember_memory(...)` writes explicit facts.
- `recall_memory(...)` retrieves relevant entries.
- `commit_memory(...)` stores a transcript after a run.
- `commit_on_forward=True` can commit automatically.

### Tool — Callable Functions for the Model

`FlowToolCall` is the model-visible tool abstraction. It owns both sides of a tool: the name, description, and JSON schema shown to the LLM, plus the Python call that executes against a `Session`.

This keeps tool schema and tool behavior together. Built-in tools cover common filesystem, shell, and code execution paths. Custom Python tools can implement the same interface, and stdio MCP tools can be adapted into the loop as normal `FlowToolCall` instances.

The important split is:

- `FlowToolCall` is the flow-layer function visible to the model.
- `BackendTool*` is the lower-level payload consumed by a sandbox backend.

### Agent — One Reusable Layer

`flow.Agent` is the small reusable layer most users start with. It is closer to `nn.Linear` than to a full application: it has a prompt, a provider, optional tools, optional memory, and a `forward(session) -> session` path.

An agent does not own the whole world. The session loop remains the engine, the sandbox remains session placement, and memory remains a separate store. This keeps the single-agent case simple while still allowing the same agent to appear inside larger workflows.

### Workflow — Compose Without Chaos

`flow.Workflow` is the composition surface. Subclasses implement:

```python
def forward(self, session: Session) -> Session:
    ...
```

A workflow can chain agents, fork sessions, compress context, call tools, dispatch to child workflows, and return a new session. Because the input and output are both `Session`, workflows can be nested without inventing a new state format at each layer.

For routing that depends on the conversation at runtime, `flow.Selector` is an LLM-backed router over self-describing workflows (each carries a `description`). It returns the next workflow to run, or a no-op `flow.EmptyWorkflow` when the task is done — so `if` / `while` stay plain Python:

```python
selector = flow.Selector(provider)
while not isinstance(
    nxt := selector.forward(session, triage, tech, wrapup), flow.EmptyWorkflow
):
    session = nxt(session)
```

---

## Quick Install

```bash
pip install openrath
```

Optional sandbox and memory integrations:

```bash
pip install "openrath[opensandbox]"
pip install "openrath[openviking]"
```

For source development:

```bash
git clone https://github.com/Rath-Team/OpenRath.git
cd OpenRath
uv sync --group dev --group docs
```

Most LLM examples use OpenAI-compatible environment variables:

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://your-gateway/v1
export OPENAI_DEFAULT_MODEL=your-model-name
```

You can also configure providers in `~/.openrath/config.json`. Environment variables take precedence.

---

## Learn By Running

The `example/` directory is a numbered learning ladder. Each script introduces one concept, keeps boilerplate in `_shared/`, and shows how the core objects fit together.

Run the first rung:

```bash
python example/01_hello_agent.py
```

| # | File | Concept | Needs a key? |
| --- | --- | --- | :---: |
| 01 | [`01_hello_agent.py`](example/01_hello_agent.py) | The smallest OpenRath program: build `flow.Agent`, call it on `Session`, stream a response. | yes |
| 02 | [`02_session_lineage.py`](example/02_session_lineage.py) | Branch a session with `fork`, cut lineage with `detach`, inspect the session graph, export JSONL. | no |
| 03 | [`03_sandbox_backend.py`](example/03_sandbox_backend.py) | Place the same session on `local` or `opensandbox` and observe where tools execute. | yes |
| 04 | [`04_tools_builtin.py`](example/04_tools_builtin.py) | Use built-in filesystem and shell tools that every loop can expose. | yes |
| 05 | [`05_custom_tool.py`](example/05_custom_tool.py) | Implement a custom `FlowToolCall` with a JSON schema and Python runtime behavior. | yes |
| 06 | [`06_mcp_tool.py`](example/06_mcp_tool.py) | Wrap a tiny stdio MCP server and borrow its tools without writing new tool classes. | no |
| 07 | [`07_streaming.py`](example/07_streaming.py) | Receive streaming deltas and inspect cumulative token usage after the run. | yes |
| 08 | [`08_compress.py`](example/08_compress.py) | Use `flow.Compressor` to reduce a long session into a smaller context session. | yes |
| 09 | [`09_memory.py`](example/09_memory.py) | Use the local memory backend to remember, recall, and optionally commit a live turn. | no |
| 10 | [`10_provider_variation.py`](example/10_provider_variation.py) | Swap model vendors by changing `Provider`, while keeping Session and Workflow code stable. | yes |
| 11 | [`11_dynamic_selector.py`](example/11_dynamic_selector.py) | Route between self-describing workflows with `flow.Selector`: `if` branching and a `while` loop that ends on `flow.EmptyWorkflow`. | yes |

Read [`example/README.md`](example/README.md) for setup details and shared helpers.

---

## Docs and Links

- Docs: [https://docs.openrath.com](https://docs.openrath.com)
- Repository: [https://github.com/Rath-Team/OpenRath](https://github.com/Rath-Team/OpenRath)
- Issues: [https://github.com/Rath-Team/OpenRath/issues](https://github.com/Rath-Team/OpenRath/issues)

Build docs locally:

```bash
uv run sphinx-build -M html docs/source docs/_build
```

---

## License

OpenRath uses a BSD-style license. See [LICENSE](LICENSE).
