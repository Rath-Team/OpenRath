(example-session-usage)=
# Session Usage

Script: `example/session_usage.py`.

This script connects the common session primitives in one path. Use it to check the mental model: create agent and user sessions, then observe how `fork()`, `detach()`, backend placement, loop, and compression change the output session.

## What it covers
| Topic | Result |
| --- | --- |
| agent session | The system prompt exists as a separate session. |
| user session | User input exists as a user-side session. |
| fork and detach | A session can copy content or break lineage. |
| backend placement | `.to("local", spec="./")` selects where tools run. |
| loop and compression | A session can be compressed after an agent loop. |

## Key code
```python
from rath import flow
from rath.session import Session, run_session_loop, run_session_compress

agent_session = Session.from_agent_prompt("You are a helpful assistant.")
user_session = Session.from_user_message(
    "Please use tool to summarize this workspace. And return the summary."
)
user_session = user_session.to("local", spec="./")

provider = flow.Provider(model="glm-5.1")
out_session = run_session_loop(
    user_session=user_session,
    agent_session=agent_session,
    agent_provider=provider,
)

compressed = run_session_compress(
    user_session=out_session,
    agent_session=agent_session,
    agent_provider=provider,
)
```

## Key lines
| Line | Explanation |
| --- | --- |
| `Session.from_agent_prompt(...)` | Creates an agent-side system session. |
| `Session.from_user_message(...)` | Creates a user-side session. |
| `.to("local", spec="./")` | Uses the current project directory as the local workspace. |
| `run_session_loop(...)` | Combines the agent session and user session, allowing the model to call tools. |
| `run_session_compress(...)` | Compresses an existing transcript into a new user-only session. |

## Run
```bash
python example/session_usage.py
```

This script requires a real LLM configuration. The model name comes from project configuration; if it is missing, the script uses its default.

## Successful output
The script prints two `Session(...)` objects. The first is the full transcript after the loop. It usually contains user and assistant rows, plus any `tool_result` rows produced by model tool calls:

```text
Session(
  id=...,
  backend='local',
  chunks=[
    [0] user: 'Please use tool to summarize this workspace...'
    [1] assistant: tools=[run_shell_command(...)]
    [2] tool_result: name='run_shell_command', ...
    [3] assistant: text='...'
  ]
)
```

The second session is the compressed result. It is usually shorter and mainly keeps the compressed user-side summary:

```text
Session(
  chunks=[
    [0] user: 'Summary: ...'
  ]
)
```

## What to inspect
| Location | What to check |
| --- | --- |
| First `print(out_session)` | The post-loop session, with assistant rows and possible tool result rows. |
| Second `print(out_session)` | The new compressed session, usually shorter and containing a new user-side summary. |
| workspace | If the model calls built-in tools, they run in the bound directory. |

## Troubleshooting
| Symptom | Check |
| --- | --- |
| LLM request fails | Check `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and the model name. |
| Tools cannot access files | Check the directory passed to `.to("local", spec="./")`. |
| Compression returns empty output | Check whether the model returned non-empty assistant content. |
| Output is long | This is the raw loop transcript; inspect the second output for the compressed result. |

## Exercises
1. Change `spec="./"` to a temporary directory and observe which files the model can see.
2. Call `fork()` before the loop and let the two sessions run different tasks.
3. Rewrite the compression prompt so the compressed result keeps a TODO list.
