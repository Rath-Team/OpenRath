# Backends and sandboxes

## Mental model

Think of `BackendSandbox` as an opaque **runtime handle** issued by a `Backend`
implementation—similar to selecting `cuda` vs `cpu`, OpenRath selects `local` vs `opensandbox`.

Tool execution always flows:

```
FlowToolCall → Backend.dispatch(sandbox, call) → ToolResult | bool
```

(`FlowToolFilesExists` collapses to `bool`.)

## Registry API

`rath.backend` exposes:

| Function | Role |
|----------|------|
| `register(name, backend_cls)` | Plug in new backends |
| `get(name)` | Resolve backend singleton |
| `list_names()` / `preferred()` | Discovery helpers |
| `set_default(name)` / `current()` | Default backend selection |

Local backend imports eagerly (`import rath.backend.local`). OpenSandbox imports attempt optional extra loading and silently skip when dependencies are absent.

## Local backend

`LocalBackend` runs commands against the host filesystem via subprocess semantics paired with `anyio.Path`.
Ideal for development parity tests (`tests/backends/test_local.py`).

## OpenSandbox backend

Installing `[opensandbox]` enables `rath.backend.opensandbox.OpenSandboxBackend`, which talks to a deployed OpenSandbox server.
Configure domains/API keys via environment variables (see `.env.example`).

Capabilities (`Capabilities`, `IsolationLevel`) describe isolation guarantees; streams/events integrate with `anyio`.

## Streams and futures

`Stream`, `Event`, and `Future` wrap sandbox-scoped async primitives so concurrent tool orchestration can mirror CUDA stream idioms without tying OpenRath to a specific GPU stack.

## Errors

Common exceptions:

- `BackendSandboxClosed` — handle reuse after teardown.
- `UnsupportedBackendTool` — backend cannot execute provided call category.
- `BackendNotFound` — registry lookup failure.
