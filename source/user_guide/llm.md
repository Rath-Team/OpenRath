# LLM client and settings

## Provider

`rath.llm.Provider` is a frozen dataclass describing **everything except** the evolving `messages`/`tools`
payload—exactly the kwargs `run_session_loop` merges into `RathLLMChatRequest`.

Typical fields:

| Field | Meaning |
|-------|---------|
| `model` | Provider-specific chat model id |
| `temperature`, `top_p`, `max_tokens`, … | Sampling knobs mirroring OpenAI SDK |
| `tool_choice`, `parallel_tool_calls` | Tool-call policy hints |

Use `flow.Provider(...)` or `rath.llm.Provider(...)` interchangeably (`flow.Agent` imports the same type).

## RathOpenAIChatClient

`RathOpenAIChatClient` wraps synchronous OpenAI-compatible HTTP calls (via `openai-python` patterns inside the implementation).

Construction reads defaults from:

- Environment variables (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, …).
- Optional `.env` through `python-dotenv`.

There is **no framework-level HTTP timeout** enforced by Rath today—operators should wrap calls if policies require hard deadlines.

## Requests and responses

`rath.llm.chat_request` / `chat_response` host dataclasses that normalize provider payloads for the loop (`RathLLMChatRequest`, `RathLLMChatResponse`, message/tool structs).

These types intentionally track OpenAI wire compatibility so swapping gateways stays localized.

## Integration point

`DefaultSessionLoopExecutor` adapts `RathOpenAIChatClient` into the `SessionLoopExecutor` protocol:

- `complete(req)` issues chat completions.
- `dispatch_tool(session, call)` forwards Flow calls into the sandbox attached to `session`.
- `tool_schemas()` exposes registrations expected by the model.

Replace `executor=` when you need tracing, caching, batching, or alternate vendors while keeping `run_session_loop` unchanged.
