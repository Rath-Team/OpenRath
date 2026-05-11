# 沙箱后端

后端负责真正执行工具。OpenRath 把“模型看到的工具”与“沙箱执行的工具载荷”分开：模型调用 `FlowToolCall`，而后端执行 `BackendTool`。

## Backend 抽象

每个后端需要实现：

| 方法 | 作用 |
| --- | --- |
| `is_available()` | 静态可用性检查，要求便宜、无网络探测。 |
| `capabilities()` | 返回 `Capabilities`，描述隔离级别和能力。 |
| `supported_calls()` | 返回支持的 `BackendTool` 类型集合。 |
| `open(spec=None)` | 打开 sandbox，返回 `BackendSandbox`。 |
| `close(sandbox)` | 关闭 sandbox。 |
| `dispatch(sandbox, call)` | 执行后端工具载荷。 |

`BackendSandbox` 是运行时句柄，持有 `backend`、`handle`、`spec` 和 `closed` 标记。它也提供 `dispatch(call)` 与 `stream(...)`。

## 注册表

公共注册 API 位于 `rath.backend`：

```python
from rath.backend import get, list_names, preferred

print(list_names())
backend = get("local")
backend = preferred(["opensandbox", "local"])
```

当前 `rath.backend.__init__` 会自动导入 `local`，并在可选依赖存在时尝试导入 `opensandbox`。

## 后端工具载荷

`BackendTool` 是后端层消费的数据类：

| 类型 | 返回 |
| --- | --- |
| `BackendToolCommandRun` | `CommandResult` |
| `BackendToolFilesRead` | `FileContent` |
| `BackendToolFilesWrite` | `FileWriteResult` |
| `BackendToolFilesList` | `FileEntries` |
| `BackendToolFilesExists` | `bool` |
| `BackendToolCodeRun` | `CodeResult` |

可以通过 `rath.flow.tool` 的工厂直接构造这些载荷：

```python
from rath.backend import get
from rath.flow.tool import flow_tool_command_run

backend = get("local")
with backend.open() as sandbox:
    result = sandbox.dispatch(flow_tool_command_run("echo hello"))
    print(result.stdout)
```

## `local` 后端

`LocalBackend` 始终可用，使用主机子进程和主机文件系统：

- 命令通过 `subprocess.run(...)` 执行；
- 相对路径解析到 sandbox working directory；
- `BackendToolCodeRun(language="python")` 会以 Python 子进程方式执行；
- `FileEntries` 会按名称排序，便于稳定测试。

如果 `open(spec=None)`，本地后端会创建一个临时目录。若 `spec.working_dir` 存在，则直接使用该目录。

注意：当前 `close(...)` 会 `shutil.rmtree(sandbox.handle)`，因此把真实项目目录绑定为 working directory 时要特别谨慎。

## `opensandbox` 后端

`OpenSandboxBackend` 是可选后端，需要 SDK、code interpreter 依赖和服务端配置。默认镜像为：

```text
opensandbox/code-interpreter:v1.0.2
```

默认 workspace root 是：

```text
/workspace
```

当 `BackendSandboxSpec(working_dir=...)` 存在时，后端会尝试把 host path 绑定到 `/workspace`。如果 OpenSandbox 服务拒绝 host bind，当前实现会在非 strict 模式下重试为空 workspace。设定：

```bash
RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND=1
```

即可禁止自动降级。

## Stream / Event

`BackendSandbox.stream()` 返回一个绑定到单个 sandbox 的 FIFO worker。它提供：

- `submit(call)`：提交后端工具载荷，返回 `Future`；
- `synchronize()`：等待当前 stream 清空；
- `record_event()` / `wait_event(...)`：跨 stream 同步；
- `query()`：查看是否空闲。

这个接口适合以后做更复杂的并发编排；当前它是线程队列封装，不是分布式调度器。

## 错误与失败

后端层的两类失败要区分：

- 框架错误：例如未知后端会抛 `BackendNotFound`；
- 工具执行失败：后端通常返回 `ToolExecutionFailure(kind, message, detail)`，让 session loop 可以把错误反馈给模型。

**下一篇：** [工具](tools.md)
