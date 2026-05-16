# LLM
OpenRath uses registry-dispatched chat clients. The default kind is OpenAI-compatible; `provider_kind="anthropic"` selects the Anthropic adapter. Advanced integrations can register a new chat client kind or replace `SessionLoopExecutor` to take over model calls, response parsing, and tool dispatch.

This page explains how OpenRath builds provider requests, normalizes responses, streams deltas, accounts for token usage, and replaces the client or executor.

The diagram below places `Provider` in the request path. Provider options,
session messages, and `FlowToolCall` schemas become one OpenAI-compatible chat
request; the normalized response is written back into the session loop.

```{figure} ../_static/core-provider.png
:alt: LLM request interface overview

`Provider` configures the request, while `Session` supplies messages and
`FlowToolCall` supplies tool definitions.
```

## Overview

The LLM layer is deliberately narrow. It does not own workflow state and it does
not execute tools. Its job is to carry provider options, build a request, call an
OpenAI-compatible client, normalize the response, and hand the result back to the
session loop.

## Source map
| File | Responsibility |
| --- | --- |
| `src/rath/llm/provider.py` | `Provider` request options. |
| `src/rath/llm/base.py` | `ChatClient` and `StreamingChatClient` protocols. |
| `src/rath/llm/registry.py` | `chat_client_for(...)` and adapter registration. |
| `src/rath/llm/openai/client.py` | `RathOpenAIChatClient`, including streaming and Azure fallback. |
| `src/rath/llm/anthropic/client.py` | `RathAnthropicChatClient`. |
| `src/rath/llm/chat_request.py` | Request dataclasses. |
| `src/rath/llm/chat_response.py` | Normalized response and stream-delta dataclasses. |
| `src/rath/llm/openai/create_kwargs.py` | Conversion from internal request to OpenAI SDK kwargs. |
| `src/rath/llm/openai/normalize.py` | Conversion from OpenAI completion to internal response. |
| `src/rath/llm/anthropic/create_kwargs.py` | Conversion from internal request to Anthropic kwargs. |
| `src/rath/llm/anthropic/normalize.py` | Conversion from Anthropic response to internal response. |
| `src/rath/session/provider_builtin.py` | Default `SessionLoopExecutor`. |

## Provider Parameters
`Provider` is the request options object. It stores the API key, optional base URL, model name, sampling parameters, tool choice, response format, and passthrough arguments.

```python
import os

from rath.llm import Provider

provider = Provider(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ.get("OPENAI_BASE_URL") or None,
    model=os.environ.get("OPENAI_DEFAULT_MODEL") or "gpt-5.5",
    temperature=0.2,
    parallel_tool_calls=False,
)
```

`provider_into_chat_request(...)` merges `Provider` into `RathLLMChatRequest`. The session loop builds messages and tools. `Provider.from_config(...)` can also load named providers from `~/.openrath/config.json`; explicit kwargs override the config entry.

## Default Client
`chat_client_for(provider)` chooses a built-in adapter or a registered third-party adapter.

| `Provider.provider_kind` | Client |
| --- | --- |
| `None` or `"openai"` | `RathOpenAIChatClient` |
| `"anthropic"` | `RathAnthropicChatClient` |

`RathOpenAIChatClient` wraps `openai.OpenAI(...).chat.completions.create(...)`; legacy Azure endpoints use `openai.AzureOpenAI`. `RathAnthropicChatClient` wraps `anthropic.Anthropic(...).messages.create(...)`.

| Environment variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | API key for OpenAI or a compatible gateway. |
| `OPENAI_BASE_URL` | OpenAI-compatible endpoint. |
| `OPENAI_DEFAULT_MODEL` | OpenAI-compatible fallback model. |
| `AZURE_OPENAI_ENDPOINT` | Azure endpoint fallback. |
| `AZURE_OPENAI_API_KEY` / `AZURE_API_KEY` | Azure key fallbacks. |
| `ANTHROPIC_API_KEY` | Anthropic API key. |
| `ANTHROPIC_BASE_URL` | Anthropic endpoint override. |
| `ANTHROPIC_DEFAULT_MODEL` | Anthropic fallback model. |

Config fallback comes after explicit `Provider` fields and environment variables. The OpenAI client looks for `provider_kind="openai"` config entries; the Anthropic client looks for `provider_kind="anthropic"`.

## Streaming
OpenAI-compatible streaming is exposed through `run_session_loop(on_event=...)`. The loop builds a `StreamingExecutor` around a `StreamingChatClient`, forwards every `RathLLMStreamDelta` to the callback, and appends one accumulated assistant chunk per model round.

Anthropic currently implements the non-streaming `ChatClient` protocol only. Passing `on_event` with `provider_kind="anthropic"` raises `TypeError` before the loop registers sessions.

## SessionLoopExecutor
`SessionLoopExecutor` is the replacement point for the loop.

```python
class SessionLoopExecutor(Protocol):
    def complete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
        ...

    def dispatch_tool(self, session, tool, arguments):
        ...

    def tool_schemas(self):
        ...
```

| Method | Purpose |
| --- | --- |
| `complete(req)` | Runs one chat completion. |
| `dispatch_tool(session, tool, arguments)` | Executes a `FlowToolCall`. |
| `tool_schemas()` | Returns tool schemas; when it returns an empty tuple, the loop builds schemas from the local tool table. |

`DefaultSessionLoopExecutor` uses `chat_client_for(agent_provider)` for model requests and directly calls `tool(session, arguments)` for tool execution.

## Requests And Responses
OpenRath uses normalized dataclasses internally:

| Type | Purpose |
| --- | --- |
| `RathLLMChatRequest` | messages, tools, model, sampling parameters, and extra args. |
| `RathLLMChatResponse` | Normalized completion. |
| `RathLLMStreamDelta` | Normalized streaming content/tool-call/usage delta. |
| `RathLLMMessage` | system/user/assistant/tool message. |
| `RathLLMFunctionTool` | OpenAI-style function tool schema. |
| `RathLLMTokenUsage` | Prompt/completion/total token usage. |

## Integration Points
| Need | Extension point |
| --- | --- |
| Change OpenAI-compatible gateway | Set `Provider.base_url` (often from `OPENAI_BASE_URL`). |
| Change model and sampling parameters | Set `Provider(...)` before passing it to the loop or client. |
| Use a local model service | Implement `SessionLoopExecutor.complete(...)`. |
| Customize tool dispatch policy | Implement `SessionLoopExecutor.dispatch_tool(...)`. |
| Test fixed model responses | Use a scripted executor. |
| Call Anthropic (`claude-*`) | `Provider(provider_kind="anthropic", model="...")`. |
| Stream assistant deltas | Pass `on_event=` to `run_session_loop(...)`; the resolved client must satisfy `StreamingChatClient`. |
| Wire an MCP server's tools | `from rath.flow.tool.mcp_adapter import mcp_tools_from_server` — `mcp` ships as a core dependency. |
| Per-session token accounting | `Session.cumulative_usage` (the loop / compress accumulate automatically). |
| Token budget guardrail | `Provider(budget_total_tokens=..., on_budget_exceeded=callback)`; the callback can `raise BudgetExceededError` to abort the loop. |
| Register a new provider | `register_chat_client("kind", factory)` and set `Provider(provider_kind="kind")`. |

## Call Path
Default session loop LLM call path:

```text
run_session_loop
  -> provider_into_chat_request(messages, tools, Provider, default_tool_choice="auto")
  -> DefaultSessionLoopExecutor.complete(req)
  -> chat_client_for(provider).complete(req)
  -> provider-specific create kwargs
  -> provider SDK call
  -> provider-specific response normalization
```

The compress path uses the same client and request/response DTOs, but passes `tools=None` and `default_tool_choice="none"`.

## Edge Cases
| Behavior | Current implementation |
| --- | --- |
| missing API key | Built-in clients raise `ValueError` after Provider/env/config fallback is exhausted. |
| missing model | Provider-specific create-kwargs builders raise `ValueError` when both `req.model` and the default model are empty. |
| streaming | OpenAI supports `complete_stream`; Anthropic raises via protocol check when `on_event` is requested. |
| tool argument parsing | `normalize_chat_completion(...)` attempts to parse arguments as JSON and records a parse error flag. |
| empty choices | `RathLLMChatResponse.primary_choice` raises `IndexError`. |
| token budget | The guard fires only on the first completion that crosses `budget_total_tokens` for the output session. |

## Test Coverage
| Behavior | Tests |
| --- | --- |
| request/response wire shape | `tests/session/test_llm_message_wire.py` |
| live OpenAI-compatible client | `tests/llm/test_openai_chat_real.py` |
| OpenAI streaming chunks | `tests/llm/test_openai_stream_chunks.py` |
| Anthropic adapter | `tests/llm/test_anthropic_client.py`, `tests/llm/test_anthropic_normalize.py` |
| provider registry | `tests/llm/test_registry.py` |
| scripted loop executor | `tests/session/scripted_loop_executor.py` |
| integration loop/compress | `tests/integration/test_session_loop_real.py`, `tests/integration/test_session_compress_real.py` |
