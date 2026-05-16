(pkg-backend)=
# `rath.backend`

Backend abstractions, sandbox handles, backend tool payloads, execution results, registry, and stream.

## Source
| Module | Source |
| --- | --- |
| `rath.backend.abc` | `src/rath/backend/abc.py` |
| `rath.backend.tool_types` | `src/rath/backend/tool_types.py` |
| `rath.backend.results` | `src/rath/backend/results.py` |
| `rath.backend.registry` | `src/rath/backend/registry.py` |
| `rath.backend.local` | `src/rath/backend/local.py` |
| `rath.backend.opensandbox` | `src/rath/backend/opensandbox.py` |
| `rath.backend.stream` | `src/rath/backend/stream.py` |
| `rath.backend.persistence` | `src/rath/backend/persistence/` |

## Public contract
### Backend interface
| API | Returns | Description |
| --- | --- | --- |
| `Backend.is_available()` | `bool` | Static availability check. |
| `Backend.capabilities()` | `Capabilities` | Backend class-level capabilities. |
| `Backend.supported_calls()` | `frozenset[type[BackendTool]]` | Supported payload types. |
| `backend.open(spec=None)` | `BackendSandbox` | Opens a sandbox handle with `refcount == 0`; bind it to a session or enter its context before holding it. |
| `backend.close(sandbox)` | `None` | Closes and releases resources. |
| `backend.dispatch(sandbox, call)` | `ToolResult` \| `bool` | Executes the payload. |

### Sandbox handle lifecycle
```{figure} ../_static/sandbox-refcount-lifecycle.png
:alt: Refcounted sandbox lifecycle

Each `Session.sandbox` slot owns one sandbox reference; the backend closes the
handle only after the final reference is released.
```

| API | Behavior |
| --- | --- |
| `sandbox.refcount` | Read-only live reference count. |
| `sandbox.acquire()` | Adds one reference; raises `BackendSandboxClosed` if closed. |
| `sandbox.release()` | Drops one reference; closes through the backend when the count reaches zero. |
| `with sandbox:` | Acquires on enter and releases on exit. |
| `sandbox.dispatch(call)` | Runs a backend payload unless the sandbox is closed. |
| `sandbox.stream(buffer=0)` | Creates a FIFO worker stream bound to this sandbox. |

Every `Session.sandbox` slot owns one reference. `Session.bind_sandbox(...)`, `Session.require_sandbox()`, `run_session_loop(...)`, `run_session_compress(...)`, `fork()`, `detach()`, and `merge()` all preserve this ownership rule.

### Sandbox spec
| Field | Type | Description |
| --- | --- | --- |
| `image` | `str` \| `None` | Image name that the backend may use. |
| `entrypoint` | `Sequence[str]` \| `None` | Entrypoint that the backend may use. |
| `env` | `Mapping[str, str]` \| `None` | Sandbox environment variables. |
| `timeout` | `timedelta` \| `None` | Sandbox lifetime or creation-timeout semantics. |
| `working_dir` | `str` \| `None` | Local working directory or OpenSandbox host bind source. |

### Backend tool payloads
| Payload | Fields | Returns |
| --- | --- | --- |
| `BackendToolCommandRun` | `cmd`, `env`, `cwd`, `stdin`, `timeout` | `CommandResult` or `ToolExecutionFailure` |
| `BackendToolFilesRead` | `path`, `encoding` | `FileContent` or `ToolExecutionFailure` |
| `BackendToolFilesWrite` | `path`, `data`, `mode` | `FileWriteResult` |
| `BackendToolFilesList` | `path` | `FileEntries` or `ToolExecutionFailure` |
| `BackendToolFilesExists` | `path` | `bool` |
| `BackendToolCodeRun` | `code`, `language`, `timeout` | `CodeResult` or `ToolExecutionFailure` |

### Registry
| Function | Behavior |
| --- | --- |
| `register(name)` | Decorator that registers a backend class. |
| `list_names()` | Returns registered backend names. |
| `get(name)` | Returns a new backend instance. |
| `get_class(name)` | Returns the backend class. |
| `is_available(name)` | Returns true when the backend is registered and class availability is true. |
| `preferred(names)` | Returns the first available backend instance. |
| `set_default(name)` / `current()` | Sets and gets the default backend. |

### Exceptions
| Exception | Trigger |
| --- | --- |
| `BackendNotFound` | `get(...)` / `get_class(...)` cannot find the backend. |
| `BackendSandboxClosed` | `BackendSandbox.dispatch(...)` is called on a closed sandbox. |
| `UnsupportedBackendTool` | The backend implementation does not support a payload type. |
| `RuntimeError` | The opensandbox backend is opened directly when the OpenSandbox SDK is missing. |

## Built-in backends
| Backend | Behavior |
| --- | --- |
| `local` | Host-side subprocess plus filesystem workspace. Automatically registered after importing `rath.backend`. |
| `opensandbox` | Optional SDK backend. The container root is `/workspace`; `working_dir` requests a host bind. |

OpenSandbox uses `opensandbox/code-interpreter:v1.0.2` by default. If a requested host bind is rejected by the server allowlist, OpenRath retries once with an empty workspace unless `RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND=1` is set.

## Persistent sandbox identities
`PersistentSandboxRegistry` stores reusable sandbox identities under `.openrath/sandboxes/`; it does not hold live `BackendSandbox` handles.

```{figure} ../_static/sandbox-identity-registry.png
:alt: Persistent sandbox identity registry

Persistent sandbox records make local working directories and OpenSandbox remote
ids discoverable across process boundaries without keeping live handles open.
```

| Backend | Storage |
| --- | --- |
| local | `.openrath/sandboxes/local/<uuid>/` working directory. |
| opensandbox | `.openrath/sandboxes/opensandbox/<uuid>.json` remote sandbox record. |

| API | Behavior |
| --- | --- |
| `alloc_local_id()` | Creates a fresh local sandbox directory. |
| `ensure_local(id)` | Creates or reuses a local sandbox directory. |
| `list_local()` / `delete_local(id)` / `prune_local(older_than=...)` | Local sandbox cleanup helpers. |
| `record_remote(backend, remote_id, spec=None)` | Stores a remote sandbox identity. |
| `load_remote(id)` / `list_remote()` / `touch_remote(id)` / `delete_remote(id)` | Remote record lifecycle helpers. |

## Autodoc
```{eval-rst}
.. autoclass:: rath.backend.Backend
   :members:

.. autoclass:: rath.backend.BackendSandbox
   :members:

.. autoclass:: rath.backend.BackendSandboxSpec
   :members:

.. autoclass:: rath.backend.BackendToolCommandRun
   :members:

.. autoclass:: rath.backend.BackendToolFilesRead
   :members:

.. autoclass:: rath.backend.BackendToolFilesWrite
   :members:

.. autoclass:: rath.backend.BackendToolFilesList
   :members:

.. autoclass:: rath.backend.BackendToolFilesExists
   :members:

.. autoclass:: rath.backend.BackendToolCodeRun
   :members:

.. autoclass:: rath.backend.CommandResult
   :members:

.. autoclass:: rath.backend.FileContent
   :members:

.. autoclass:: rath.backend.FileEntries
   :members:

.. autoclass:: rath.backend.FileWriteResult
   :members:

.. autoclass:: rath.backend.CodeResult
   :members:

.. autoclass:: rath.backend.ToolExecutionFailure
   :members:

.. autoclass:: rath.backend.Stream
   :members:

.. autoclass:: rath.backend.Event
   :members:

.. autoclass:: rath.backend.Future
   :members:

.. autoclass:: rath.backend.persistence.PersistentSandboxRegistry
   :members:

.. autoclass:: rath.backend.persistence.RemoteSandboxRecord
   :members:

.. autofunction:: rath.backend.get

.. autofunction:: rath.backend.preferred
```

[← API Reference](index.md)
