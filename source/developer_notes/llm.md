# LLM
OpenRath uses an OpenAI-compatible chat client by default. Advanced integrations can replace `SessionLoopExecutor` to take over model calls, response parsing, and tool dispatch.

This page explains how OpenRath builds OpenAI-compatible requests, normalizes responses, and replaces the client or executor.

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
| `src/rath/llm/client.py` | `RathOpenAIChatClient`. |
| `src/rath/llm/chat_request.py` | Request dataclasses. |
| `src/rath/llm/chat_response.py` | Normalized response dataclasses. |
| `src/rath/llm/openai_create_kwargs.py` | Conversion from internal request to OpenAI SDK kwargs. |
| `src/rath/llm/openai_normalize.py` | Conversion from OpenAI completion to internal response. |
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

`provider_into_chat_request(...)` merges `Provider` into `RathLLMChatRequest`. The session loop builds messages and tools.

## Default Client
`RathOpenAIChatClient` wraps `openai.OpenAI(api_key=..., base_url=...).chat.completions.create(...)`.

| Environment variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | API key for OpenAI or a compatible gateway. |
| `OPENAI_BASE_URL` | OpenAI-compatible endpoint. |
| `OPENAI_DEFAULT_MODEL` | Conventional environment variable used by repository examples when constructing a `Provider`. |

The default client currently uses the synchronous, non-streaming chat completion path. `to_create_kwargs(...)` forces `stream=False`.

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

`DefaultSessionLoopExecutor` uses `RathOpenAIChatClient` for model requests and directly calls `tool(session, arguments)` for tool execution.

## Requests And Responses
OpenRath uses normalized dataclasses internally:

| Type | Purpose |
| --- | --- |
| `RathLLMChatRequest` | messages, tools, model, sampling parameters, and extra args. |
| `RathLLMChatResponse` | Normalized non-streaming completion. |
| `RathLLMMessage` | system/user/assistant/tool message. |
| `RathLLMFunctionTool` | OpenAI-style function tool schema. |

## Integration Points
| Need | Extension point |
| --- | --- |
| Change OpenAI-compatible gateway | Set `Provider.base_url` (often from `OPENAI_BASE_URL`). |
| Change model and sampling parameters | Set `Provider(...)` before passing it to the loop or client. |
| Use a local model service | Implement `SessionLoopExecutor.complete(...)`. |
| Customize tool dispatch policy | Implement `SessionLoopExecutor.dispatch_tool(...)`. |
| Test fixed model responses | Use a scripted executor. |
| Call Anthropic (`claude-*`) | `Provider(provider_kind="anthropic", model="...")`. |
| Stream assistant deltas | `from rath.session.loop_stream import run_session_loop_stream`, pass an `on_event=` callback. |
| Wire an MCP server's tools | `from rath.flow.tool.mcp_adapter import mcp_tools_from_server` — `mcp` ships as a core dependency. |
| Per-session token accounting | `Session.cumulative_usage` (the loop / compress accumulate automatically). |
| Token budget guardrail | `Provider(budget_total_tokens=..., on_budget_exceeded=callback)`; the callback can `raise BudgetExceededError` to abort the loop. |

## Call Path
Default session loop LLM call path:

```text
run_session_loop
  -> provider_into_chat_request(messages, tools, Provider, default_tool_choice="auto")
  -> DefaultSessionLoopExecutor.complete(req)
  -> RathOpenAIChatClient.complete(req)
  -> to_create_kwargs(req, default_model=provider.model)
  -> openai.OpenAI(...).chat.completions.create(**kwargs)
  -> normalize_chat_completion(completion)
```

The compress path uses the same client and request/response DTOs, but passes `tools=None` and `default_tool_choice="none"`.

## Edge Cases
| Behavior | Current implementation |
| --- | --- |
| missing API key | `RathOpenAIChatClient(provider)` and the default session loop raise `ValueError`. |
| missing model | `to_create_kwargs(...)` raises `ValueError` when both `req.model` and the default model are empty. |
| streaming | Raises `ValueError` when `extra_create_args["stream"] is True`; final kwargs set `stream=False`. |
| tool argument parsing | `normalize_chat_completion(...)` attempts to parse arguments as JSON and records a parse error flag. |
| empty choices | `RathLLMChatResponse.primary_choice` raises `IndexError`. |

## Test Coverage
| Behavior | Tests |
| --- | --- |
| request/response wire shape | `tests/session/test_llm_message_wire.py` |
| live OpenAI-compatible client | `tests/llm/test_openai_chat_real.py` |
| scripted loop executor | `tests/session/scripted_loop_executor.py` |
| integration loop/compress | `tests/integration/test_session_loop_real.py`, `tests/integration/test_session_compress_real.py` |
