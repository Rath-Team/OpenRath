# 沙箱后端

读完 [会话与数据块](session.md) 后，下一层是**工具调用实际运行之处**：`Backend` 颁发 `BackendSandbox` 句柄并执行 `FlowToolCall` 载荷。理解沙箱后，继续 [工具与 ToolTable](tools.md)，查看线上工具名如何解析为这些调用。

## 心智模型

把 `BackendSandbox` 看成由 `Backend` 实现颁发的**不透明运行时句柄**——类似选择 `cuda` 与 `cpu`，OpenRath 在 `local` 与 `opensandbox` 等之间选择。

工具执行路径恒为：

```
FlowToolCall → Backend.dispatch(sandbox, call) → ToolResult | bool
```

（`FlowToolFilesExists` 坍缩为 `bool`。）

## 注册表 API

`rath.backend` 暴露：

| 函数 | 作用 |
|------|------|
| `register(name, backend_cls)` | 注册新后端 |
| `get(name)` | 解析后端单例 |
| `list_names()` / `preferred()` | 发现辅助 |
| `set_default(name)` / `current()` | 默认后端选择 |

本地后端会急切加载（`import rath.backend.local`）。OpenSandbox 会在可选依赖缺失时尝试加载并不报错跳过。

## 本地后端

`LocalBackend` 借助 `anyio.Path` 在主机文件系统上以子进程语义执行命令，适合作开发/一致性测试（如 `tests/backends/test_local.py`）。

## OpenSandbox 后端

安装 `[opensandbox]` 后可使用 `rath.backend.opensandbox.OpenSandboxBackend`，与已部署的 OpenSandbox 服务通信。域名与 API 密钥等通过**进程环境变量**配置（例如 `OPEN_SANDBOX_DOMAIN`）。

`Capabilities`、`IsolationLevel` 描述隔离级别；流/事件与 `anyio` 集成。

## 流与 Future

`Stream`、`Event`、`Future` 封装沙箱范围内的异步原语，便于并发编排类比 CUDA stream 的用法，而不把 OpenRath 绑死在某一 GPU 栈上。

## 错误

常见异常：

- `BackendSandboxClosed` — 拆除后仍复用句柄。
- `UnsupportedBackendTool` — 后端无法执行给定类别的调用。
- `BackendNotFound` — 注册表查找失败。

---

**下一篇：** [工具](tools.md)
