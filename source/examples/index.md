# Examples

The `example/` directory ships runnable scripts. Execute them from the repository root
after installing OpenRath (and optional extras as noted).

| Script | Highlights |
|--------|------------|
| `example/workflow_usage.py` | `Workflow` + `Agent` + synchronous `run_session_loop` |
| `example/session_usage.py` | Session construction / inspection |
| `example/custom_tool_usage.py` | Registering tools on `ToolTable` |
| `example/sandbox_backend_local.py` | Local backend sandbox binding |
| `example/sandbox_backend_opensandbox.py` | OpenSandbox backend (requires extra + server) |

```{note}
Examples assume `.env` (or exported variables) provides API credentials when LLM calls are live.
```
