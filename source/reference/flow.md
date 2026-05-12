(pkg-flow)=
# `rath.flow`

`rath.flow` 包：对编排相关类型的再导出，以及 `Workflow`、`AgentParam` 等子模块。用户指南：[Workflow 与 AgentParam](../user_guide/workflow_agent.md)。

## `rath.flow`

自子模块再导出 `Workflow`、`Provider`、`AgentParam` 等，便于 `import rath.flow as flow` 单入口写法。

## `rath.flow.workflow`

* `Workflow` 基类：`forward(session)`、`named_agents()`、`__call__` 委托。
* 与 `rath.session.run_session_loop` 的典型配合方式。

## `rath.flow.agent_param`

* `AgentParam`：`agent_session`（系统/开发者分块）与 `provider`（采样与路由字段）的绑定体。

## `rath.flow.agent`

* `Agent`：`Workflow` 的便捷子类（示例中常用 `flow.Agent(...)` 快速搭建循环）。

## `rath.flow.compressor`

* `Compressor`：对会话历史做压缩/整理的辅助（与 `run_session_compress` 等配合使用，见 `rath.session`）。

---

[← API 参考](index.md)
