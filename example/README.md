# OpenRath examples

A numbered learning ladder. Each script introduces **one** concept and builds
on the ones before it. Read them in order, or jump to the rung you need.

The examples are deliberately small and use one shared helper module
(`_shared/`) so the OpenRath surface — not boilerplate — stays in focus.

## Setup

Most examples need a single OpenAI-compatible LLM key. Configure it once, two
ways (env vars take precedence):

```bash
export OPENAI_API_KEY=sk-...
# optional:
export OPENAI_BASE_URL=https://your-gateway/v1
export OPENAI_DEFAULT_MODEL=your-model-name
```

…or set `llm.default_provider` in `~/.openrath/config.json`. Examples never
hardcode a model, so your configured default is what runs.

Run any example from the repository root:

```bash
python example/01_hello_agent.py
```

## The ladder

| # | File | Concept | Needs a key? |
|---|------|---------|:---:|
| 01 | [01_hello_agent.py](01_hello_agent.py) | `flow.Agent` — the smallest program | yes |
| 02 | [02_session_lineage.py](02_session_lineage.py) | `fork` / `detach`, the session graph, JSONL export | **no** |
| 03 | [03_sandbox_backend.py](03_sandbox_backend.py) | `.to(backend, spec=...)` — local vs opensandbox | yes |
| 04 | [04_tools_builtin.py](04_tools_builtin.py) | built-in filesystem / shell tools | yes |
| 05 | [05_custom_tool.py](05_custom_tool.py) | your own `FlowToolCall` (local calculator) | yes |
| 06 | [06_mcp_tool.py](06_mcp_tool.py) | borrow tools from an MCP server | **no** |
| 07 | [07_streaming.py](07_streaming.py) | streaming deltas + token usage | yes |
| 08 | [08_compress.py](08_compress.py) | `flow.Compressor` to shrink context | yes |
| 09 | [09_memory.py](09_memory.py) | `flow.Agent(memory=...)`: remember / recall / commit | **no**\* |
| 10 | [10_provider_variation.py](10_provider_variation.py) | swap the LLM vendor via `Provider` | yes |
| 11 | [11_dynamic_selector.py](11_dynamic_selector.py) | `flow.Selector` — LLM-routed `if` / `while` over workflows | yes |
| 12 | [12_compile.py](12_compile.py) | `Workflow.compile()` — static resource manifest, offline `validate()`, lifecycle | **no** |

\* 09 runs key-free using the local memory backend; a key only unlocks an
optional live turn at the end.

## How these map onto PyTorch

OpenRath borrows PyTorch's shape. The ladder walks the same analogy:

| PyTorch | OpenRath | Shown in |
|---------|----------|----------|
| `Tensor` | `Session` | 01, 02 |
| compute graph | session graph (`parent_session_ids`) | 02 |
| `tensor.to(device)` | `session.to(backend)` | 03 |
| kernel / op | tool (`FlowToolCall`) | 04, 05, 06 |
| `nn.Parameter` | `flow.AgentParam` / `Provider` | 01, 10 |
| `nn.Module` | `flow.Agent` / `flow.Workflow` | 01, 08 |
| control flow | `flow.Selector` | 11 |
| `torch.compile` | `Workflow.compile()` | 12 |

## Shared helpers (`_shared/`)

- `provider.py` — `provider_from_env()` builds a `Provider` from env or
  `~/.openrath/config.json`; `has_credentials()` lets a demo skip the LLM part.
- `events.py` — `stream_to_stdout()` is the standard `on_event` callback.
- `echo_mcp_server.py` — a tiny stdio MCP server used by example 06.
