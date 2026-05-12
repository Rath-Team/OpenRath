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

## Public contract
### Backend interface
| API | Returns | Description |
| --- | --- | --- |
| `Backend.is_available()` | `bool` | Static availability check. |
| `Backend.capabilities()` | `Capabilities` | Backend class-level capabilities. |
| `Backend.supported_calls()` | `frozenset[type[BackendTool]]` | Supported payload types. |
| `backend.open(spec=None)` | `BackendSandbox` | Opens a sandbox handle. |
| `backend.close(sandbox)` | `None` | Closes and releases resources. |
| `backend.dispatch(sandbox, call)` | `ToolResult` \| `bool` | Executes the payload. |

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

.. autofunction:: rath.backend.get

.. autofunction:: rath.backend.preferred
```

[← API Reference](index.md)
