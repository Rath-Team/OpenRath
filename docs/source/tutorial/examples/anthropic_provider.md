# Anthropic Provider

This page maps to `example/anthropic_provider.py`.

## What it covers
| Step | API |
| --- | --- |
| Select Anthropic | `Provider(provider_kind="anthropic", model="...")`. |
| Reuse OpenRath flow | `flow.Agent`, `Session`, and `run_session_loop` stay unchanged. |
| Inspect usage | Anthropic responses normalize into `RathLLMTokenUsage`. |

Run:

```bash
python example/anthropic_provider.py
```

Credentials can come from `ANTHROPIC_API_KEY` or a config provider with `provider_kind="anthropic"`.

```json
{
  "llm": {
    "default_provider": "claude",
    "providers": {
      "claude": {
        "provider_kind": "anthropic",
        "model": "claude-sonnet-4-5",
        "api_key": "sk-ant-..."
      }
    }
  }
}
```

The current Anthropic adapter is non-streaming. Use it without `on_event`.

