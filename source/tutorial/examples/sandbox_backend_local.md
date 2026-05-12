(example-sandbox-local)=
# Local Backend

Script: `example/sandbox_backend_local.py`.

The key local backend difference is `spec`: omitting `spec` creates a temporary empty workspace, while passing a path makes tools run in that directory. This script puts both paths side by side so you can compare which files the agent can see.

## What it covers
| Topic | Result |
| --- | --- |
| backend availability | The script first checks whether the local backend is available. |
| empty workspace | `spec=None` opens a temporary empty directory. |
| bound workspace | `spec="."` uses the project directory as the workspace. |
| agent tool path | When the agent calls built-in tools, they run in the current session sandbox. |
| close behavior | The local backend manages directory lifetimes; be careful when binding a real directory. |

## Key code
```python
from rath.session import Session

user_session = Session.from_user_message(
    "List all files in the current directory. And summarize the result."
)

user_session = user_session.to("local", spec=None)
out_session = agent(user_session)

user_session = user_session.to("local", spec=".")
out_session = agent(user_session)
```

## Two workspace modes
| Form | Behavior | Use when |
| --- | --- | --- |
| `spec=None` | The local backend creates a temporary directory. | You want to verify tool execution without touching project files. |
| `spec="."` | The string is interpreted as `BackendSandboxSpec(working_dir=".")`. | You want tools to read the current project directory. |

## Run
```bash
python example/sandbox_backend_local.py
```

This requires a real LLM configuration because the script uses `flow.Agent` and lets the model decide whether to call tools. The model name comes from project configuration; if it is missing, the script uses its default.

## Successful output
The script first prints the initial backend target, usually `None`. It then prints two assistant replies: the first from the temporary empty workspace, and the second from the workspace bound to the project directory.

```text
None
The workspace appears to be empty.
The current directory contains files such as pyproject.toml, src/, tests/, docs/, ...
```

The exact text depends on the model. To check success, focus on whether the second reply mentions files or directories from the current repository.

## What to inspect
| Stage | What to check |
| --- | --- |
| Initial output | `user_session.sandbox_backend` is usually empty at first. |
| `spec=None` | The model sees a temporary empty workspace. |
| `spec="."` | The model can list the current project directory. |
| Last assistant row | The script prints `out_session.chunk_table.rows[-1].payload["content"]`. |

## Troubleshooting
| Symptom | Check |
| --- | --- |
| backend unavailable | Confirm that the core package is installed and the local backend is registered. |
| LLM request fails | Check the model gateway configuration. |
| File list is empty | You may be in the `spec=None` stage. |
| Tools accessed the real project directory | Confirm that the current stage is `spec="."`, and handle write requests carefully. |

## Exercises
1. Change `spec="."` to `.workspace/local-demo`.
2. Modify the user prompt so the agent creates a file and then reads it.
3. Print all `tool_result` rows and observe how command output enters the session.
