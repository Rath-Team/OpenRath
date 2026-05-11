# 沙箱（Sandbox）

Sandbox 是 OpenRath 执行工具副作用的位置。`Backend` 负责打开 sandbox、关闭 sandbox、执行 backend tool payload。

本页回答：OpenRath 如何注册 backend，`Session` 如何绑定 sandbox，local 和 OpenSandbox 的生命周期、目录映射与隔离边界如何工作。

## 源码地图（Source Map）

| 文件 | 负责内容 |
| --- | --- |
| `src/rath/backend/abc.py` | `Backend`、`BackendSandbox`、`BackendSandboxSpec`。 |
| `src/rath/backend/registry.py` | backend registry、default backend、preferred selection。 |
| `src/rath/backend/local.py` | host-side local backend。 |
| `src/rath/backend/opensandbox.py` | optional OpenSandbox backend。 |
| `src/rath/backend/tool_types.py` | backend payload dataclasses。 |
| `src/rath/backend/results.py` | backend result dataclasses。 |
| `src/rath/backend/stream.py` | stream/event/future concurrency helpers。 |

## 后端注册表（Backend Registry）

公共注册 API 位于 `rath.backend`。

```python
from rath.backend import get, list_names, preferred

print(list_names())
backend = get("local")
backend = preferred(["opensandbox", "local"])
```

当前 backend：

| Backend | 可用性 | Isolation level | 主要能力 |
| --- | --- | --- | --- |
| `local` | 导入 `rath.backend` 后自动注册，始终可用 | `PROCESS` | command、filesystem、code interpreter |
| `opensandbox` | 安装 optional extra 且环境配置满足时注册 | `CONTAINER` | command、filesystem、code interpreter |

## 会话绑定（Session Binding）

`Session` 与 sandbox 通过 backend target 或 open handle 绑定。

```python
from rath.session import Session

session = Session.from_user_message("List files.").to("local")

with session:
    sandbox = session.require_sandbox()
    print(sandbox.backend.name)
```

生命周期顺序：

| 阶段 | 方法 | 行为 |
| --- | --- | --- |
| target | `session.to("local", spec=...)` | 记录 backend 名称和 open spec。 |
| open | `session.require_sandbox()` | 按 target 打开 sandbox handle。 |
| transfer | `session.take_sandbox()` | loop 把输入 session 的 handle 转移到输出 session。 |
| close | `session.close_sandbox()` | 释放当前 handle。 |

## 本地后端（Local Backend）

`LocalBackend` 使用 host-side subprocess 和本地文件系统。

| 行为 | 实现 |
| --- | --- |
| open | `spec.working_dir` 存在时使用该目录；未提供时创建 `tempfile.mkdtemp(prefix="rath-local-")`。 |
| relative path | 相对路径基于 sandbox handle 指向的工作目录解析。 |
| command | `subprocess.run(...)`，默认 `cwd` 是 sandbox 工作目录。 |
| code | 写入临时 Python 文件并用当前 Python 执行。 |
| close | 标记 closed，并删除 sandbox handle 对应目录。 |

绑定真实目录时，需要把该目录视为 `LocalBackend` 管理的 workspace。关闭 sandbox 会触发目录清理。

## OpenSandbox 后端（OpenSandbox Backend）

`OpenSandboxBackend` 使用 optional `opensandbox` SDK 和 `code_interpreter` 包。它把 OpenRath 的 backend payload 映射到 OpenSandbox API。

| 行为 | 实现 |
| --- | --- |
| availability | 检查 SDK、code interpreter、`OPEN_SANDBOX_DOMAIN` / `OPENSANDBOX_DOMAIN` 或 `~/.sandbox.toml`。 |
| default image | `opensandbox/code-interpreter:v1.0.2`。 |
| workspace root | 容器内 `/workspace`。 |
| host bind | `BackendSandboxSpec.working_dir` 会被请求绑定到 `/workspace`。 |
| fallback | host bind 被服务拒绝时，默认重试为空 workspace；严格模式由 `RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND=1` 控制。 |
| async bridge | SDK 的 async 调用运行在 dedicated event loop thread 上，对外暴露 blocking API。 |

## 边界（Boundary）

`local` 适合开发、测试和可信 workload。需要更严格隔离时，把 session 绑定到 `opensandbox` 或后续 backend。

## 分发矩阵（Dispatch Matrix）

| Payload | local | opensandbox |
| --- | --- | --- |
| `BackendToolCommandRun` | `subprocess.run(...)` | `native.commands.run(...)` |
| `BackendToolFilesRead` | local filesystem read | OpenSandbox filesystem read |
| `BackendToolFilesWrite` | local filesystem write | OpenSandbox filesystem write |
| `BackendToolFilesList` | local directory listing | OpenSandbox filesystem search/list |
| `BackendToolFilesExists` | `Path.exists()` | OpenSandbox filesystem lookup |
| `BackendToolCodeRun` | temporary Python script | `CodeInterpreter` |

## 边界条件（Boundary Conditions）

| 行为 | 当前实现 |
| --- | --- |
| closed sandbox dispatch | `BackendSandbox.dispatch(...)` 抛 `BackendSandboxClosed`；backend-level dispatch 返回 `ToolExecutionFailure`。 |
| unsupported payload | backend 返回 `ToolExecutionFailure(kind="unsupported_tool")` 或抛 `UnsupportedBackendTool` 后转 failure。 |
| local close | 删除 sandbox handle 指向的目录。 |
| local absolute path | absolute path 原样使用。 |
| opensandbox host bind rejection | 默认重试为空 `/workspace`，严格模式由 `RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND=1` 控制。 |
| opensandbox stdin | `BackendToolCommandRun.stdin` 返回 unsupported failure。 |

## 测试覆盖（Test Coverage）

| 行为 | 测试 |
| --- | --- |
| local lifecycle | `tests/backends/test_local.py` |
| opensandbox lifecycle | `tests/backends/test_opensandbox.py` |
| command payload | `tests/conformance/test_command_run.py` |
| file payloads | `tests/conformance/test_files.py` |
| code payload | `tests/conformance/test_code_run.py` |
| stream/event | `tests/conformance/test_stream_event.py`, `tests/unit/test_stream.py` |
| backend registry | `tests/unit/test_registry.py` |
| opensandbox bind fallback | `tests/unit/test_opensandbox_bind_fallback.py`, `tests/unit/test_opensandbox_workspace_volume.py` |
