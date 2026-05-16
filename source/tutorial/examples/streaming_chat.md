# Streaming Chat

This page maps to `example/streaming_chat.py`.

## What it covers
| Step | API |
| --- | --- |
| Configure an OpenAI-compatible provider | `Provider(model=...)` plus env/config fallback. |
| Receive live assistant text | `run_session_loop(on_event=...)`. |
| Preserve structured transcript | The loop still appends one accumulated assistant chunk per round. |
| Inspect cost | `out.cumulative_usage`. |

Run:

```bash
python example/streaming_chat.py
```

Credentials can come from `OPENAI_API_KEY` or an `llm.default_provider` entry in `~/.openrath/config.json`. `on_event` requires a client that implements `StreamingChatClient`; the built-in OpenAI-compatible client does, while the Anthropic adapter currently does not.

## Key pattern
```python
def on_event(delta):
    if delta.content_delta:
        print(delta.content_delta, end="", flush=True)

out = run_session_loop(
    user,
    agent.agent_session,
    agent_provider=agent.provider,
    on_event=on_event,
)
```

## Troubleshooting
| Symptom | Check |
| --- | --- |
| `TypeError: on_event requires a StreamingChatClient` | Drop `on_event` or switch to an OpenAI-compatible provider. |
| No API key found | Export `OPENAI_API_KEY` or configure an OpenAI provider in `~/.openrath/config.json`. |

