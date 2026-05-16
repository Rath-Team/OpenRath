---
orphan: true
---

# Project Status

OpenRath is currently a usable core runtime with active hardening around durability, provider integrations, and contributor workflow. The project is past the pure prototype stage: the main abstractions are implemented in `src/rath`, covered by tests, documented in the API reference, and exercised by runnable examples. It is not yet a fully polished platform with long-term compatibility guarantees for every new integration.

```text
Core model          Runtime path          Durability layer        Project quality
Session/Workflow -> LLM loop + tools  ->  persistence/config  ->  CI/docs/examples
Backend/Tooling     local/OpenSandbox     local JSON/JSONL        Ruff + Actions
```

```{figure} _static/release-highlights-overview.png
:alt: OpenRath v1.1.0 release highlights overview

OpenRath v1.1.0 expands the runtime around provider integrations, durability,
tooling, and project quality.
```

## Current Stage

| Layer | Status | What this means |
| --- | --- | --- |
| Session core | Implemented and central | `Session` carries transcript chunks, sandbox placement, lineage, usage, and branch operations. |
| Workflow API | Implemented | `Workflow`, `Agent`, `AgentParam`, and `Compressor` provide the main composition surface. |
| Tool runtime | Implemented | `FlowToolCall` bridges model-visible schemas to backend side effects. |
| Local backend | Usable | Local command, file, and code payloads are supported and covered by conformance tests. |
| OpenSandbox backend | Integrated, still operationally sensitive | Container execution works, with workspace bind fallback and CI coverage, but depends on external service/runtime setup. |
| LLM providers | Expanded | OpenAI-compatible and Anthropic adapters exist behind a provider registry. |
| Streaming | Implemented for compatible clients | `run_session_loop(on_event=...)` supports streaming deltas while keeping durable assistant chunks. |
| Persistence | Implemented, still early UX | Session JSONL persistence and sandbox identity registry exist, but higher-level user workflows are still being documented. |
| MCP integration | Implemented as adapter | Stdio MCP tools can be wrapped as `FlowToolCall`; transport scope is intentionally narrow. |
| CI and lint | In place | Ruff, pre-commit, and GitHub Actions now cover lint, docs, tests, shellcheck, and OpenSandbox paths. |
| Documentation | Being brought in line with source | API reference and tutorials now cover the new surface; deeper guides are still being expanded. |

## What Is Stable Enough To Build On

These areas are the current foundation of the project:

| Capability | Evidence in repo |
| --- | --- |
| Session state model | `src/rath/session/session.py`, `chunk.py`, `loop.py`, `compress.py` |
| Workflow composition | `src/rath/flow/workflow.py`, `agent.py`, `agent_param.py`, `compressor.py` |
| Backend abstraction | `src/rath/backend/abc.py`, `local.py`, `tool_types.py`, `results.py` |
| LLM request/response DTOs | `src/rath/llm/chat_request.py`, `chat_response.py` |
| OpenAI-compatible client path | `src/rath/llm/openai/` |
| Core tutorials/examples | `docs/source/tutorial/`, `example/session_usage.py`, `example/sandbox_backend_local.py` |
| Test coverage shape | `tests/session/`, `tests/backends/`, `tests/llm/`, `tests/flow/`, `tests/conformance/` |

The repository currently has dozens of focused test files across session behavior, backends, provider adapters, persistence, MCP, and conformance. That makes the codebase closer to an early framework than a one-off demo.

## What Recently Moved From Design Into Runtime

The latest development line adds a durability and integration layer around the core runtime:

| Area | Runtime change |
| --- | --- |
| Provider ecosystem | Registry-based dispatch through `chat_client_for(...)`, plus Anthropic support. |
| Config | Persistent `~/.openrath/config.json` with LLM provider and MCP server sections. |
| Session persistence | Append-only JSONL writer/loader with crash detection and resumable pairs. |
| Sandbox persistence | Local workspace and OpenSandbox remote identity registry. |
| Sandbox lifecycle | Refcounted live handles shared by loop outputs, forks, detaches, and merges. |
| Merge primitive | `Session.merge(...)` combines compatible branches and records merge lineage. |
| Streaming loop | `on_event` callback receives `RathLLMStreamDelta` values from streaming clients. |
| MCP tools | Stdio MCP servers can be exposed to the loop as normal `FlowToolCall` tools. |
| LLM resilience | Retry policy, credential fallback, token usage accounting, and budget guardrail. |
| Project operations | Ruff migration, pre-commit, and GitHub Actions CI matrix. |

```{figure} _static/ci-tooling-pipeline.png
:alt: OpenRath CI and tooling pipeline

The current contributor path is guarded by Ruff, type checks, tests, docs builds,
and GitHub Actions workflows.
```

## What Still Needs Productization

These are the main areas that need continued work before the project feels like a mature public platform:

| Area | Current gap |
| --- | --- |
| Persistence UX | Low-level APIs exist; user-facing resume/cleanup workflows need clearer tutorials and examples. |
| Config UX | JSON config is implemented; CLI helpers or guided setup are not yet present. |
| MCP scope | Stdio transport works; HTTP/SSE transports are not part of the current adapter. |
| OpenSandbox operations | Backend integration exists; production deployment still depends on server/runtime configuration. |
| Docs coverage | Public API reference and tutorials are aligned with v1.1.0; excluded `user_guide` source is being synchronized but is not published in this site build. |
| Release communication | Long-form announcement content should live on `blog.openrath.com`, not inside this docs site. |
| Compatibility policy | Current release is `v1.1.0`; new extension points should be treated as evolving until maintainers publish a stricter policy. |

## Practical Interpretation

For a new user:

- OpenRath is ready to try for local agent workflows, structured session experiments, custom tools, and provider integration work.
- It is especially useful if you want session state, tool execution, and workflow composition to be explicit Python objects.
- For production use, validate provider credentials, sandbox lifecycle, persistence cleanup, and OpenSandbox deployment in your environment.

For a contributor:

- The next highest-value work is not inventing new abstractions; it is tightening the user path around the abstractions that now exist.
- Good follow-up work includes persistence tutorials, config setup helpers, OpenSandbox deployment notes, MCP transport expansion, and docs images for the new runtime layers.
