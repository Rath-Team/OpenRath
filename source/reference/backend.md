(pkg-backend)=
# `rath.backend`

后端抽象、sandbox handle、backend tool payload、执行结果、注册表和 stream。

## 源码（Source）

| 模块 | 源码 |
| --- | --- |
| `rath.backend.abc` | `src/rath/backend/abc.py` |
| `rath.backend.tool_types` | `src/rath/backend/tool_types.py` |
| `rath.backend.results` | `src/rath/backend/results.py` |
| `rath.backend.registry` | `src/rath/backend/registry.py` |
| `rath.backend.local` | `src/rath/backend/local.py` |
| `rath.backend.opensandbox` | `src/rath/backend/opensandbox.py` |
| `rath.backend.stream` | `src/rath/backend/stream.py` |

## 公共契约（Public Contract）

### 后端接口（Backend Interface）

| API | 返回 | 说明 |
| --- | --- | --- |
| `Backend.is_available()` | `bool` | 静态可用性检查。 |
| `Backend.capabilities()` | `Capabilities` | backend class 级别能力。 |
| `Backend.supported_calls()` | `frozenset[type[BackendTool]]` | 支持的 payload 类型。 |
| `backend.open(spec=None)` | `BackendSandbox` | 打开 sandbox handle。 |
| `backend.close(sandbox)` | `None` | 关闭并释放资源。 |
| `backend.dispatch(sandbox, call)` | `ToolResult` \| `bool` | 执行 payload。 |

### 沙箱规格（Sandbox Spec）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `image` | `str` \| `None` | backend 可选择使用的镜像名。 |
| `entrypoint` | `Sequence[str]` \| `None` | backend 可选择使用的 entrypoint。 |
| `env` | `Mapping[str, str]` \| `None` | sandbox 环境变量。 |
| `timeout` | `timedelta` \| `None` | sandbox 生命周期或创建超时语义。 |
| `working_dir` | `str` \| `None` | local 工作目录或 OpenSandbox host bind 来源。 |

### 后端工具载荷（Backend Tool Payloads）

| Payload | 字段 | 返回 |
| --- | --- | --- |
| `BackendToolCommandRun` | `cmd`, `env`, `cwd`, `stdin`, `timeout` | `CommandResult` 或 `ToolExecutionFailure` |
| `BackendToolFilesRead` | `path`, `encoding` | `FileContent` 或 `ToolExecutionFailure` |
| `BackendToolFilesWrite` | `path`, `data`, `mode` | `FileWriteResult` |
| `BackendToolFilesList` | `path` | `FileEntries` 或 `ToolExecutionFailure` |
| `BackendToolFilesExists` | `path` | `bool` |
| `BackendToolCodeRun` | `code`, `language`, `timeout` | `CodeResult` 或 `ToolExecutionFailure` |

### 注册表（Registry）

| 函数 | 行为 |
| --- | --- |
| `register(name)` | 注册 backend class 的装饰器。 |
| `list_names()` | 返回已注册 backend name。 |
| `get(name)` | 返回 backend 新实例。 |
| `get_class(name)` | 返回 backend class。 |
| `is_available(name)` | backend 已注册且 class availability 为 true。 |
| `preferred(names)` | 返回第一个可用 backend 实例。 |
| `set_default(name)` / `current()` | 设置和获取默认 backend。 |

### 异常（Exceptions）

| 异常 | 触发位置 |
| --- | --- |
| `BackendNotFound` | `get(...)` / `get_class(...)` 找不到 backend。 |
| `BackendSandboxClosed` | 已关闭 sandbox 调用 `BackendSandbox.dispatch(...)`。 |
| `UnsupportedBackendTool` | backend 实现不支持某种 payload。 |
| `RuntimeError` | OpenSandbox SDK 缺失时直接打开 opensandbox backend。 |

## 内置后端（Built-in Backends）

| Backend | 行为 |
| --- | --- |
| `local` | host-side subprocess + filesystem workspace；导入 `rath.backend` 后自动注册。 |
| `opensandbox` | optional SDK backend；容器 root 为 `/workspace`，`working_dir` 会请求 host bind。 |

## 自动文档（Autodoc）

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

[← API 参考](index.md)
