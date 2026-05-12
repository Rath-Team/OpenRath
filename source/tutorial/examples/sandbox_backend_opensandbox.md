(example-sandbox-opensandbox)=
# OpenSandbox Backend

Script: `example/sandbox_backend_opensandbox.py`.

The OpenSandbox path and local path use the same `Session.to(...)` entry point. The differences are the backend name, server connection configuration, and workspace bind strategy; the agent-side code stays the same.

## What it covers
| Topic | Result |
| --- | --- |
| backend switch | `Session.to("opensandbox", spec=...)` selects OpenSandbox. |
| service dependency | The OpenSandbox backend requires a reachable external service. |
| empty workspace | `spec=None` maps to an empty `/workspace` in the container. |
| workspace bind | `spec="."` attempts to bind the host path into the container workspace. |
| strict mode | On bind failure, you can retry with an empty workspace or fail immediately. |

## Prerequisites
1. Install the OpenSandbox extra.
2. Start a service compatible with the OpenSandbox API.
3. Configure the OpenSandbox domain and API key.
4. For host path binding, make sure the server `allowed_host_paths` permits the path.

Example commands:

```bash
pip install -e ".[opensandbox]"
export OPEN_SANDBOX_DOMAIN=127.0.0.1:8080
export OPEN_SANDBOX_API_KEY=...
```

Run a health check first:

```bash
python - <<'PY'
import rath.backend as backend

b = backend.get("opensandbox")
print("available:", b.is_available())
print("capabilities:", b.capabilities())
PY
```

## Key code
```python
user_session = Session.from_user_message(
    "List all files in the current directory. And summarize the result."
)

user_session = user_session.to("opensandbox", spec=None)
out_session = agent(user_session)

user_session = user_session.to("opensandbox", spec=".")
out_session = agent(user_session)
```

## Workspace bind behavior
| Form | Behavior |
| --- | --- |
| `spec=None` | Creates an OpenSandbox workspace without binding a host path. |
| `spec="."` | Attempts to bind the current directory to container `/workspace`. |
| strict mode off | If the host bind is rejected, the backend can fall back to an empty workspace. |
| strict mode on | If the host bind is rejected, the backend fails immediately. |

The repository `scripts/launch_opensandbox.sh` writes the current project directory into `.sandbox.toml` under `allowed_host_paths`. If you start OpenSandbox manually or point `spec` to another directory, update the allowlist yourself.

To fail strictly:

```bash
export RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND=1
```

## Run
```bash
python example/sandbox_backend_opensandbox.py
```

This script needs both a real LLM configuration and OpenSandbox service configuration.

## Successful output
Like the local backend example, the script first prints the initial backend target, then runs the empty workspace and bound workspace stages:

```text
None
The /workspace directory is empty.
The workspace contains files such as pyproject.toml, src/, tests/, docs/, ...
```

If the `spec="."` bind succeeds, the second output mentions files from the current repository. If the server rejects the host bind and strict mode is off, the second output may still look like an empty workspace; check `allowed_host_paths` in `.sandbox.toml`.

## What to inspect
| Stage | What to check |
| --- | --- |
| availability check | `main` runs only when `backend.get("opensandbox").is_available()` is true. |
| `spec=None` | The agent sees an empty workspace in the container. |
| `spec="."` | If the service allows the bind, the agent can see the bound directory. |
| fallback behavior | In non-strict mode, execution may continue after bind failure. |

## Troubleshooting
| Symptom | Check |
| --- | --- |
| backend unavailable | Check the extra, OpenSandbox SDK, and environment variables. |
| Service connection fails | Check `OPEN_SANDBOX_DOMAIN`, the server port, and the API key. |
| host bind is rejected | Check the server allowed host paths. |
| agent cannot see project files | Confirm that the `spec="."` stage actually bound the directory. |

## Exercises
1. Change `spec="."` to `.workspace/opensandbox-demo`.
2. Enable strict mode, intentionally bind a disallowed path, and observe the error.
3. Compare the `tool_result` output from the local backend and OpenSandbox backend.
