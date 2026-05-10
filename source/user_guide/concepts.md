# Design overview

OpenRath adopts a **metaphor consistent with PyTorch-style ergonomics** without
being a wrapper around PyTorch itself:

- **Stateful tape** — A [`Session`](session.md) holds ordered conversation chunks
  (system, user, assistant, tool results). Think of it as the primary carrier object
  you thread through a workflow.
- **Composition** — A [`Workflow`](workflow_agent.md) aggregates named [`AgentParam`](workflow_agent.md)
  instances via attribute assignment, similar to submodules on `nn.Module`.
- **Functional tool payloads** — Structured calls (`FlowToolCall`) are built with
  small factories under `rath.flow.tool`, analogous to `torch.nn.functional` style helpers.
- **Backends** — Sandboxes (`BackendSandbox`) and concurrency helpers (`Stream`,
  `Event`) mirror the idea of selecting a **device** or runtime for execution.

This mental model is descriptive: OpenRath does **not** embed autograd or tensors.

## Stable versus experimental

Documentation follows the same rough split as [PyTorch documentation](https://docs.pytorch.org/docs/stable/index.html):

**Stable** areas include core dataclasses (`Session`, `AgentParam`, `Provider`),
`run_session_loop`, `Workflow`, the `FlowToolCall` hierarchy, and `Backend.dispatch`.

**Experimental** areas include remote sandbox binding details, optional extras wiring,
and any hooks marked provisional in source docstrings—verify behavior against tests
when upgrading.

## Layering

| Layer | Packages | Responsibility |
|-------|-----------|----------------|
| Flow façade | `rath.flow` | `Workflow`, `AgentParam`, tool table helpers |
| Session runtime | `rath.session` | Chunks, lineage, registry, session loop |
| LLM I/O | `rath.llm` | OpenAI-compatible requests/responses, client |
| Execution | `rath.backend` | Sandbox handles, dispatch, results, streams |

Import rule of thumb: **`rath.flow.tool` defines tool call values**; **`rath.backend`**
executes them on a sandbox. `rath.flow.tool` does **not** import `rath.backend`.
