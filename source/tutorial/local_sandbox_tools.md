# Local Sandbox Tools

Before involving a model, look at where tools actually execute. This page opens `LocalBackend` directly, dispatches file, command, and code payloads by hand, and shows how they operate around the same local workspace.

## Coverage
| Topic | Result |
| --- | --- |
| Backend registry | How `get("local")` returns the local Backend. |
| Sandbox handle | A local sandbox maps to one working directory. |
| Backend payload | File, command, and code execution are represented by `BackendTool*` data classes. |
| Structured result | Each dispatch returns a structured object. |
| Lifecycle | `backend.close(sandbox)` closes the sandbox and may clean up the working directory. |

## Step 1: Open the Local Backend
```python
from rath.backend import get

backend = get("local")
sandbox = backend.open()

print(backend.name)
print(backend.capabilities())
print(sandbox.handle)
```

Key lines:

| Line | Explanation |
| --- | --- |
| `get("local")` | Gets the local Backend instance from the Backend registry. |
| `backend.open()` | Creates a `BackendSandbox` handle. |
| `sandbox.handle` | The workspace path managed by the local Backend. |

Observed behavior:

- `backend.name` is `local`.
- `sandbox.handle` is a local path.
- If no `working_dir` is passed, the local Backend creates a temporary directory.

## Step 2: Write and Read a File
```python
from rath.backend import BackendToolFilesRead, BackendToolFilesWrite

write_result = sandbox.dispatch(
    BackendToolFilesWrite(path="hello.txt", data="hello OpenRath")
)
content = sandbox.dispatch(
    BackendToolFilesRead(path="hello.txt", encoding="utf-8")
)

print(write_result)
print(content)
```

Key lines:

| Line | Explanation |
| --- | --- |
| `BackendToolFilesWrite(...)` | Describes a file write without executing it directly. |
| `sandbox.dispatch(...)` | Sends the payload to the current sandbox for execution. |
| `BackendToolFilesRead(...)` | Reads the file just written in the same workspace. |

Observed behavior:

- The write result includes the number of bytes written.
- The read result includes the file content.
- The relative path `hello.txt` is resolved from `sandbox.handle`.

## Step 3: Run a Shell Command
```python
from rath.backend import BackendToolCommandRun

result = sandbox.dispatch(
    BackendToolCommandRun(cmd="pwd && cat hello.txt")
)

print(result.exit_code)
print(result.stdout.decode())
print(result.stderr.decode())
```

Key lines:

| Line | Explanation |
| --- | --- |
| `BackendToolCommandRun(...)` | Describes a shell command execution. |
| `exit_code` | Lets the caller decide whether the command succeeded. |
| `stdout` / `stderr` | The current implementation stores output as bytes, so callers need to decode it. |

Observed behavior:

- `pwd` prints the directory for the local sandbox workspace.
- `cat hello.txt` can read the content written in the previous step.
- When a command fails, check `exit_code` and `stderr` first.

## Step 4: Run Python Code
```python
from rath.backend import BackendToolCodeRun

result = sandbox.dispatch(
    BackendToolCodeRun(code="print(21 * 2)")
)

print(result.stdout.decode())
print(result.stderr.decode())
print(result.error)
```

The current local Backend writes the code to a temporary Python file, then runs it with the current Python interpreter. This is useful for checking tool paths and script behavior. Use a stricter isolated Backend for untrusted code.

## Step 5: Close the Sandbox
```python
backend.close(sandbox)
print(sandbox.closed)
```

Key points:

| Behavior | Notes |
| --- | --- |
| `backend.close(sandbox)` | Closes the sandbox handle. |
| Local workspace cleanup | The local Backend cleans up directories it manages. |
| Bound directory risk | When binding a real directory, make sure it can be recreated to reduce the risk of deleting important content. |

## Troubleshooting
| Symptom | Check |
| --- | --- |
| `get("local")` fails | Confirm OpenRath is installed and `rath.backend` imports correctly. |
| File cannot be read | Confirm the write and read happen on the same sandbox. |
| Command has no output | Print `exit_code` and `stderr.decode()` first. |
| Dispatch fails after close | Re-run `backend.open()` after the sandbox is closed. |

## Exercises
1. Change `hello.txt` to `notes/hello.txt` and observe whether the directory is created automatically.
2. Rewrite the shell command so it lists all files under the workspace.
3. Change the Python code so it reads `hello.txt` and prints its length.

## Summary

- `BackendTool*` payloads describe Backend-side operations.
- `BackendSandbox.dispatch(...)` executes a payload and returns a structured result.
- File, command, and code payloads operate around the same sandbox workspace.
- Built-in tools in the Session loop eventually run through this Backend dispatch layer.
