(pkg-backend)=
# `rath.backend`

沙箱句柄、工具在隔离环境中的执行、注册表与结果类型。用户指南：[后端与沙箱](../user_guide/backends.md)。

## `rath.backend`

对外门面：注册表 API、沙箱类型、结果与时间线/能力枚举等。

## `rath.backend.abc`

`Backend`、`BackendSandbox`、`BackendSandboxSpec` 等协议定义。

## `rath.backend.local`

主机子进程/本地文件系统语义后端。

## `rath.backend.opensandbox`

对接已部署 OpenSandbox 服务的适配器（可选 `[opensandbox]` extra）。

## `rath.backend.registry`

按名称注册与查找后端实现。

## `rath.backend.results`

`CommandResult`、`FileContent`、`CodeResult` 及错误/失败结构体。

## `rath.backend.stream`

`Stream`、`Event`、`Future` 等沙箱侧并发抽象。

## `rath.backend.tool_types`

后端侧工具载荷数据类（与 flow 层 `FlowToolCall` 对齐的别名）。

---

[← API 参考](index.md)
