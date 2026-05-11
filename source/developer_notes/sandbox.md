# Sandbox

Sandbox 是 OpenRath 中承载工具副作用的运行位置。模型请求工具时，最终会通过 `Session` 找到 active sandbox，再由 backend 执行命令、文件或代码 payload。

本页说明 backend 注册、`Session` 绑定 sandbox、local/OpenSandbox 生命周期差异、目录映射方式，以及 backend 选择标准。

## 概览

`Session` 保存执行位置，`Backend` 负责打开和执行，`BackendSandbox` 是一次打开后的 handle。

| 层次 | 代表对象 | 负责内容 |
| --- | --- | --- |
| 选择 backend | `session.to("local")`、`session.to("opensandbox")` | 记录执行位置。 |
| 打开 runtime | `Backend.open(spec)` | 创建本地目录或容器 sandbox。 |
| 执行 payload | `sandbox.dispatch(call)` | 运行 command、filesystem、code payload。 |
| 释放资源 | `Backend.close(sandbox)` | 关闭 handle，释放目录或容器。 |

这套分层让同一个 `FlowToolCall` 可以在不同 backend 上执行。工具构造 backend payload；local 和 OpenSandbox 分别决定 payload 的执行方式。

## 源码地图

| 文件 | 负责内容 |
| --- | --- |
| `src/rath/backend/abc.py` | `Backend`、`BackendSandbox`、`BackendSandboxSpec`。 |
| `src/rath/backend/registry.py` | backend registry、default backend、preferred selection。 |
| `src/rath/backend/local.py` | host-side local backend。 |
| `src/rath/backend/opensandbox.py` | optional OpenSandbox backend。 |
| `src/rath/backend/tool_types.py` | backend payload dataclasses。 |
| `src/rath/backend/results.py` | backend result dataclasses。 |
| `src/rath/backend/stream.py` | stream/event/future concurrency helpers。 |

## Backend 抽象

所有 backend 都实现同一个抽象接口：

| 方法 | 作用 |
| --- | --- |
| `is_available()` | 判断当前环境是否能使用该 backend。 |
| `capabilities()` | 返回隔离级别和能力说明。 |
| `supported_calls()` | 返回支持的 backend payload 类型。 |
| `open(spec)` | 打开 sandbox，返回 `BackendSandbox`。 |
| `close(sandbox)` | 关闭 sandbox 并释放资源。 |
| `dispatch(sandbox, call)` | 执行 backend payload。 |

`BackendSandboxSpec` 是打开 sandbox 时的可选配置：

| 字段 | 用途 |
| --- | --- |
| `image` | 容器类 backend 可用的镜像名。 |
| `entrypoint` | 容器启动入口。 |
| `env` | 打开 sandbox 时传入的环境变量。 |
| `timeout` | sandbox 生命周期或操作 timeout。 |
| `working_dir` | workspace 目录；local 直接使用，OpenSandbox 尝试绑定到 `/workspace`。 |

## Backend registry

Backend 通过 `@register(name)` 注册。公共 API 位于 `rath.backend`。

```python
from rath.backend import get, is_available, list_names, preferred

print(list_names())
print(is_available("opensandbox"))

backend = preferred(["opensandbox", "local"])
```

当前主要 backend：

| Backend | 可用性 | Isolation level | 主要能力 |
| --- | --- | --- | --- |
| `local` | 导入 `rath.backend` 后自动注册，始终可用。 | `PROCESS` | command、filesystem、code interpreter |
| `opensandbox` | 安装 optional extra，且存在环境变量或 `~/.sandbox.toml`。 | `CONTAINER` | command、filesystem、code interpreter |

`preferred([...])` 会返回第一个已注册且 `is_available()` 为 true 的 backend 实例。它适合写“优先用 OpenSandbox，环境不满足时用 local”的开发脚本。

## Session 如何绑定 sandbox

`Session` 可以只记录 target，也可以绑定已经打开的 handle。

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
| lazy open | `session.require_sandbox()` | 按 target 打开 sandbox handle。 |
| transfer | `session.take_sandbox()` | loop 把输入 session 的 handle 转移到输出 session。 |
| close | `session.close_sandbox()` | 释放当前 handle，保留 backend target。 |

`run_session_loop(...)` 会调用 `user_session.take_sandbox()`。因此 loop 结束后，输入 user session 通常不再持有 `sandbox`；输出 session 接管同一个 handle。

## local backend

`LocalBackend` 在当前机器上执行 payload。它始终可用，适合开发、单元测试和可信 workload。

| 行为 | 当前实现 |
| --- | --- |
| open | 如果 `spec.working_dir` 存在，就使用该目录；否则创建 `tempfile.mkdtemp(prefix="rath-local-")`。 |
| relative path | 相对路径基于 sandbox handle 指向的工作目录解析。 |
| absolute path | 原样使用 absolute path。 |
| command | 非 Windows 使用 `/bin/sh -c`；Windows 使用 shell command。 |
| code | 写入临时 Python 文件，并用当前 Python 解释器执行。 |
| close | 标记 closed，并 `shutil.rmtree(sandbox.handle, ignore_errors=True)`。 |

local backend 的关键风险在 `close`：它会删除 handle 对应的目录。把真实项目目录作为 `working_dir` 时，应将该目录视为可重建 workspace。

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

`OpenSandboxBackend` 使用 optional `opensandbox` SDK 和 `code_interpreter` 包，把 backend payload 映射到 OpenSandbox API。

| 行为 | 当前实现 |
| --- | --- |
| availability | 检查 SDK、code interpreter、`OPEN_SANDBOX_DOMAIN` / `OPENSANDBOX_DOMAIN` 或 `~/.sandbox.toml`。 |
| API reachability | `is_available()` 不 ping server，只做本地配置检查。 |
| default image | `opensandbox/code-interpreter:v1.0.2`。 |
| default entrypoint | `/opt/opensandbox/code-interpreter.sh`。 |
| workspace root | 容器内 `/workspace`。 |
| async bridge | SDK async 调用运行在 dedicated event loop thread 上，对外提供 blocking API。 |

OpenSandbox 的 `working_dir` 会被解析为 host path，并请求绑定到容器内 `/workspace`。这个 host path 必须对 OpenSandbox server 所在机器可见。

```python
from rath.session import Session

session = Session.from_user_message("List workspace.")
session.to("opensandbox", spec=".")
```

OpenSandbox server 使用 `.sandbox.toml` 中的 `storage.allowed_host_paths` 判断 host path 是否允许绑定。仓库启动脚本会把当前项目目录加入 allowlist；手动启动 server 或绑定其他目录时，需要同步更新该列表。如果 server 拒绝 host bind，OpenRath 默认重试为空 workspace。设置 `RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND=1` 后，bind 被拒绝时会直接失败，便于发现配置问题。

## 选择 local 还是 OpenSandbox

| 场景 | Backend | 原因 |
| --- | --- | --- |
| 写文档 tutorial、跑单元测试 | `local` | 启动快，依赖少，行为容易观察。 |
| 调试工具 schema 和 session loop | `local` | 能快速看到文件、stdout、stderr。 |
| 需要容器环境或依赖隔离 | `opensandbox` | 工具副作用发生在容器 workspace。 |
| 验证 OpenSandbox 集成 | `opensandbox` | 覆盖 SDK、server、workspace bind、code interpreter。 |
| 处理不可信 workload | `opensandbox` 或后续更强隔离 backend | local 使用 host-side subprocess 和文件系统。 |

这里的选择标准来自当前实现。local 的 isolation level 是 `PROCESS`，OpenSandbox 的 isolation level 是 `CONTAINER`。

## Payload 分发矩阵

| Payload | local | opensandbox |
| --- | --- | --- |
| `BackendToolCommandRun` | `subprocess.run(...)` | `native.commands.run(...)` |
| `BackendToolFilesRead` | local filesystem read | OpenSandbox filesystem read |
| `BackendToolFilesWrite` | local filesystem write | OpenSandbox filesystem write |
| `BackendToolFilesList` | local directory listing | OpenSandbox filesystem search/list |
| `BackendToolFilesExists` | `Path.exists()` | OpenSandbox filesystem lookup |
| `BackendToolCodeRun` | temporary Python script | `CodeInterpreter` |

OpenSandbox 的 `BackendToolCommandRun.stdin` 当前返回 unsupported failure。`BackendToolCodeRun.language` 只支持 `bash`、`go`、`java`、`javascript`、`python`、`typescript`。

## Stream API

`BackendSandbox.stream()` 可以在同一个 sandbox 上组织 backend payload。

| 行为 | 语义 |
| --- | --- |
| same stream | FIFO queue，单 worker thread 顺序执行。 |
| different streams | 不同 worker thread 可并发推进。 |
| event | `record_event()` 和 `wait_event(...)` 可建立跨 stream 顺序。 |
| synchronize | 等待当前 stream 已提交操作完成。 |

session loop 当前逐个处理模型返回的 tool calls。stream 更适合手动写 backend-level 并发流程。

## 健康检查与验证

OpenSandbox server 启动后，可以先检查 control plane：

```bash
curl -fsS http://127.0.0.1:8080/health
```

健康检查只说明 server 响应。OpenRath example 会继续验证 backend client、容器 runtime 和 workspace bind：

```bash
python example/sandbox_backend_opensandbox.py
```

这一步能覆盖 OpenRath client 配置、sandbox open、command/file/code payload，以及 workspace bind 行为。

## 边界条件

| 行为 | 当前实现 |
| --- | --- |
| closed sandbox 调用 `BackendSandbox.dispatch(...)` | 抛 `BackendSandboxClosed`。 |
| backend-level dispatch 遇到 closed sandbox | 返回 `ToolExecutionFailure(kind="sandbox_closed")`。 |
| unsupported payload | 返回 `ToolExecutionFailure(kind="unsupported_tool")` 或相关 failure。 |
| local close | 删除 sandbox handle 指向的目录。 |
| local absolute path | absolute path 原样使用。 |
| local command timeout | 返回 `ToolExecutionFailure(kind="timeout")`。 |
| OpenSandbox bind 被拒绝 | 默认重试为空 `/workspace`；严格模式关闭重试。 |
| OpenSandbox stdin | 返回 unsupported failure。 |
| OpenSandbox unsupported language | 返回 `ToolExecutionFailure(kind="unsupported_tool")`。 |

## 读代码时的检查点

| 想确认的问题 | 看哪里 |
| --- | --- |
| backend 抽象接口 | `src/rath/backend/abc.py` |
| backend 注册与选择 | `src/rath/backend/registry.py` |
| local close 是否删除目录 | `src/rath/backend/local.py::close` |
| OpenSandbox bind fallback | `src/rath/backend/opensandbox.py::_create_sandbox_with_optional_bind_fallback` |
| payload 类型 | `src/rath/backend/tool_types.py` |
| result 类型 | `src/rath/backend/results.py` |
| stream 行为 | `src/rath/backend/stream.py` |

## 测试覆盖

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
