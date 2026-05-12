(pkg-session)=
# `rath.session`

会话状态、会话循环与分块「磁带」相关的运行时。用户指南：[会话与数据块](../user_guide/session.md)、[Workflow 与循环](../user_guide/workflow_agent.md)。

## `rath.session`

* `Session`、分块与消息桥接工具、`run_session_loop`、`SessionLoopExecutor`。
* 会话原语（如 `fork_session` 等）。
* 谱系图与 `session_registry`。

## `rath.session.chunk`

`ChunkTable`、行级辅助、`format_chunk_row_brief`、与聊天消息结构的转换。

## `rath.session.graph`

`SessionLineage`、`LineageRecorder`、图遍历。

## `rath.session.loop`

供 `Workflow` / `run_session_loop` 共用的循环实现细节；含 `ChunkAppendHook`、`sink_chunk_print`
（逐块打印一行摘要）与 `run_session_loop` 的 ``chunk_print=`` 契约。

## `rath.session.manager`

`SessionRegistry` 与全局注册钩子。

## `rath.session.provider_builtin`

`DefaultSessionLoopExecutor`（默认同步执行器）。

## `rath.session.primitives`

其它会话变换/实验性辅助。

在接入 `sphinx-autosummary` 前，以源码模块 docstring 为准。

---

[← API 参考](index.md)
