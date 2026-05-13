# Sandbox

Sandbox is where OpenRath runs tool side effects. When the model requests a tool, the runtime finds the active sandbox through `Session`, then the backend executes command, file, or code payloads.

This page explains backend registration, how `Session` binds a sandbox, lifecycle differences between local and OpenSandbox, directory mapping, and backend selection.

The diagram below is the execution boundary for this page. A session records the
target backend, the registry resolves an implementation, and the sandbox executes
typed payloads behind that boundary.

```{figure} ../_static/core-backend.png
:alt: Backend boundary overview

Backend execution is intentionally separated from model-facing tools: tools
produce typed payloads, and the selected backend decides how those payloads run.
```

## Overview

`Session` stores execution placement, `Backend` opens and executes work, and `BackendSandbox` is the handle for one opened runtime.

| Layer | Object | Responsibility |
| --- | --- | --- |
| Choose backend | `session.to("local")`, `session.to("opensandbox")` | Records execution placement. |
| Open runtime | `Backend.open(spec)` | Creates a local directory or container sandbox. |
| Execute payload | `sandbox.dispatch(call)` | Runs command, filesystem, and code payloads. |
| Release resources | `Backend.close(sandbox)` | Closes the handle and releases the directory or container. |

This layering lets the same `FlowToolCall` run on different backends. The tool builds a backend payload; local and OpenSandbox decide how that payload is executed.

## Source map

| File | Responsibility |
| --- | --- |
| `src/rath/backend/abc.py` | `Backend`, `BackendSandbox`, `BackendSandboxSpec`. |
| `src/rath/backend/registry.py` | Backend registry, default backend, preferred selection. |
| `src/rath/backend/local.py` | host-side local backend. |
| `src/rath/backend/opensandbox.py` | optional OpenSandbox backend. |
| `src/rath/backend/tool_types.py` | backend payload dataclasses. |
| `src/rath/backend/results.py` | backend result dataclasses. |
| `src/rath/backend/stream.py` | stream/event/future concurrency helpers. |

## Backend Abstraction

All backends implement the same abstract interface:

| Method | Purpose |
| --- | --- |
| `is_available()` | Checks whether this backend can be used in the current environment. |
| `capabilities()` | Returns isolation level and capability details. |
| `supported_calls()` | Returns supported backend payload types. |
| `open(spec)` | Opens a sandbox and returns `BackendSandbox`. |
| `close(sandbox)` | Closes the sandbox and releases resources. |
| `dispatch(sandbox, call)` | Executes a backend payload. |

`BackendSandboxSpec` holds optional settings for opening a sandbox:

| Field | Purpose |
| --- | --- |
| `image` | Image name for container backends. |
| `entrypoint` | Container entrypoint. |
| `env` | Environment variables passed when opening the sandbox. |
| `timeout` | Sandbox lifecycle or operation timeout. |
| `working_dir` | Workspace directory; local uses it directly, OpenSandbox tries to bind it to `/workspace`. |

## Backend registry

Backends are registered with `@register(name)`. The public API lives in `rath.backend`.

```python
from rath.backend import get, is_available, list_names, preferred

print(list_names())
print(is_available("opensandbox"))

backend = preferred(["opensandbox", "local"])
```

The main backends are:

| Backend | Availability | Isolation level | Main capabilities |
| --- | --- | --- | --- |
| `local` | Automatically registered after importing `rath.backend`; always available. | `PROCESS` | command, filesystem, code interpreter |
| `opensandbox` | Optional extra is installed and environment variables or `~/.sandbox.toml` exist. | `CONTAINER` | command, filesystem, code interpreter |

`preferred([...])` returns the first registered backend whose `is_available()` is true. It is useful for development scripts that prefer OpenSandbox and fall back to local when the environment is not configured.

## How Session Binds Sandbox

`Session` can record only a target, or it can bind an already-open handle.

```python
from rath.session import Session

session = Session.from_user_message("List files.").to("local")

with session:
    sandbox = session.require_sandbox()
    print(sandbox.backend.name)
```

Lifecycle order:

| Stage | Method | Behavior |
| --- | --- | --- |
| target | `session.to("local", spec=...)` | Records the backend name and open spec. |
| lazy open | `session.require_sandbox()` | Opens a sandbox handle from the target. |
| transfer | `session.take_sandbox()` | Loop transfers the input session handle to the output session. |
| close | `session.close_sandbox()` | Releases the current handle and keeps the backend target. |

`run_session_loop(...)` calls `user_session.take_sandbox()`. After the loop finishes, the input user session usually no longer holds `sandbox`; the output session owns the same handle.

## local backend

`LocalBackend` executes payloads on the current machine. It is always available and fits development, unit tests, and trusted workloads.

| Behavior | Current implementation |
| --- | --- |
| open | Uses `spec.working_dir` if present; otherwise creates `tempfile.mkdtemp(prefix="rath-local-")`. |
| relative path | Resolves relative paths from the working directory pointed to by the sandbox handle. |
| absolute path | Uses the absolute path as provided. |
| command | Uses `/bin/sh -c` outside Windows; uses shell command on Windows. |
| code | Writes a temporary Python file and runs it with the current Python interpreter. |
| close | Marks closed and calls `shutil.rmtree(sandbox.handle, ignore_errors=True)`. |

The main risk in the local backend is `close`: it deletes the directory referenced by the handle. If a real project directory is used as `working_dir`, treat it as a rebuildable workspace.

```python
from rath.backend import BackendToolFilesWrite
from rath.session import Session

session = Session.from_user_message("write").to("local")
with session:
    result = session.require_sandbox().dispatch(
        BackendToolFilesWrite(path="note.txt", data="hello")
    )
    print(result.bytes_written)
```

## OpenSandbox backend

`OpenSandboxBackend` uses the optional `opensandbox` SDK and `code_interpreter` package to map backend payloads to the OpenSandbox API.

| Behavior | Current implementation |
| --- | --- |
| availability | Checks SDK, code interpreter, `OPEN_SANDBOX_DOMAIN` / `OPENSANDBOX_DOMAIN`, or `~/.sandbox.toml`. |
| API reachability | `is_available()` does not ping the server; it only checks local configuration. |
| default image | `opensandbox/code-interpreter:v1.0.2`. |
| default entrypoint | `/opt/opensandbox/code-interpreter.sh`. |
| workspace root | `/workspace` inside the container. |
| async bridge | SDK async calls run on a dedicated event loop thread and expose a blocking API outward. |

OpenSandbox resolves `working_dir` to a host path and requests a bind mount at `/workspace` inside the container. That host path must be visible from the machine running the OpenSandbox server.

```python
from rath.session import Session

session = Session.from_user_message("List workspace.")
session.to("opensandbox", spec=".")
```

The OpenSandbox server checks `storage.allowed_host_paths` in `.sandbox.toml` to decide whether a host path can be bound. The repository startup script adds the current project directory to the allowlist; if the server is started manually or another directory is bound, update that list as well. If the server rejects the host bind, OpenRath retries with an empty workspace by default. Set `RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND=1` to fail immediately on bind rejection, which makes configuration problems easier to find.

## Choosing local Or OpenSandbox

| Scenario | Backend | Reason |
| --- | --- | --- |
| Writing docs tutorials or running unit tests | `local` | Starts quickly, has few dependencies, and is easy to inspect. |
| Debugging tool schemas and session loop | `local` | Files, stdout, and stderr are easy to observe. |
| Need a container environment or dependency isolation | `opensandbox` | Tool side effects happen in a container workspace. |
| Validating OpenSandbox integration | `opensandbox` | Covers SDK, server, workspace bind, and code interpreter. |
| Handling untrusted workloads | `opensandbox` or a later stronger-isolation backend | local uses host-side subprocesses and filesystem access. |

These choices reflect the current implementation. local has isolation level `PROCESS`; OpenSandbox has isolation level `CONTAINER`.

## Payload Dispatch Matrix

| Payload | local | opensandbox |
| --- | --- | --- |
| `BackendToolCommandRun` | `subprocess.run(...)` | `native.commands.run(...)` |
| `BackendToolFilesRead` | local filesystem read | OpenSandbox filesystem read |
| `BackendToolFilesWrite` | local filesystem write | OpenSandbox filesystem write |
| `BackendToolFilesList` | local directory listing | OpenSandbox filesystem search/list |
| `BackendToolFilesExists` | `Path.exists()` | OpenSandbox filesystem lookup |
| `BackendToolCodeRun` | temporary Python script | `CodeInterpreter` |

OpenSandbox currently returns an unsupported failure for `BackendToolCommandRun.stdin`. `BackendToolCodeRun.language` supports only `bash`, `go`, `java`, `javascript`, `python`, and `typescript`.

## Stream API

`BackendSandbox.stream()` can organize backend payloads on the same sandbox.

| Behavior | Semantics |
| --- | --- |
| same stream | FIFO queue, one worker thread, sequential execution. |
| different streams | Different worker threads can make progress concurrently. |
| event | `record_event()` and `wait_event(...)` can create ordering across streams. |
| synchronize | Waits for already-submitted operations in the current stream to finish. |

The session loop currently handles model-returned tool calls one by one. Streams are more useful for manually written backend-level concurrent flows.

## Health Check And Validation

After the OpenSandbox server starts, first check the control plane:

```bash
curl -fsS http://127.0.0.1:8080/health
```

The health check only proves that the server responds. The OpenRath example also validates the backend client, container runtime, and workspace bind:

```bash
python example/sandbox_backend_opensandbox.py
```

This covers OpenRath client configuration, sandbox open, command/file/code payloads, and workspace bind behavior.

## Edge Cases

| Behavior | Current implementation |
| --- | --- |
| `BackendSandbox.dispatch(...)` on a closed sandbox | Raises `BackendSandboxClosed`. |
| backend-level dispatch on a closed sandbox | Returns `ToolExecutionFailure(kind="sandbox_closed")`. |
| unsupported payload | Returns `ToolExecutionFailure(kind="unsupported_tool")` or a related failure. |
| local close | Deletes the directory pointed to by the sandbox handle. |
| local absolute path | Uses the absolute path as provided. |
| local command timeout | Returns `ToolExecutionFailure(kind="timeout")`. |
| OpenSandbox bind rejected | Retries with empty `/workspace` by default; strict mode disables retry. |
| OpenSandbox stdin | Returns unsupported failure. |
| OpenSandbox unsupported language | Returns `ToolExecutionFailure(kind="unsupported_tool")`. |

## Code Reading Checkpoints

| Question | Where to look |
| --- | --- |
| Backend abstract interface | `src/rath/backend/abc.py` |
| Backend registration and selection | `src/rath/backend/registry.py` |
| Whether local close deletes the directory | `src/rath/backend/local.py::close` |
| OpenSandbox bind fallback | `src/rath/backend/opensandbox.py::_create_sandbox_with_optional_bind_fallback` |
| Payload types | `src/rath/backend/tool_types.py` |
| Result types | `src/rath/backend/results.py` |
| Stream behavior | `src/rath/backend/stream.py` |

## Test Coverage

| Behavior | Tests |
| --- | --- |
| local lifecycle | `tests/backends/test_local.py` |
| opensandbox lifecycle | `tests/backends/test_opensandbox.py` |
| command payload | `tests/conformance/test_command_run.py` |
| file payloads | `tests/conformance/test_files.py` |
| code payload | `tests/conformance/test_code_run.py` |
| stream/event | `tests/conformance/test_stream_event.py`, `tests/unit/test_stream.py` |
| backend registry | `tests/unit/test_registry.py` |
| opensandbox bind fallback | `tests/unit/test_opensandbox_bind_fallback.py`, `tests/unit/test_opensandbox_workspace_volume.py` |
