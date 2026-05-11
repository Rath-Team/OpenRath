# 会话

## Session

`Session` 是主要的**会话载体**，包含：

- **`chunk_table`** — 按 `ChunkKind`（`system`、`user`、`assistant`、`tool_result` 等）标记的有序行。
- **沙箱字段** — 可选绑定到 `BackendSandbox` 以及打开会话时使用的后端名。

`Session` 上的工厂方法包括：

- `Session.from_user_message(text)` — 仅用用户轮次播种，无 system 前言。
- `Session.from_agent_prompt(prompt)` — 播种 system / 智能体侧指令。

## 绑定沙箱

调用 `Session.to(backend_name, spec=...)` 可打开或改绑沙箱执行。`spec` 可为 `BackendSandboxSpec`，或由后端解释的**工作目录字符串**。

下游的 `run_session_loop` 会把沙箱归属**重定**到返回的会话上，使工具分发对准当前工作流输出。下一章 [后端与沙箱](backends.md) 说明这些分发如何执行。

## 分块工具

模块 `rath.session` 导出 `chunk_table_to_messages`、`assistant_turn_chunk`、`tool_feedback_chunk` 等，用于在循环实现里把分块表桥接到 LLM 线格式。

## 谱系与注册表

开启图跟踪（`session_graph_mode()`）时，循环产生的新会话会打上谱系元数据，并经 `session_registry` 注册。由此可查询出处（`SessionLineage`、日志等），类似追踪中间结果的产生路径——但**没有**梯度。

## 原语

`rath.session.primitives` 提供 `fork_session`、`merge_sessions`、`detach_session` 等，用于操作分块历史。在专用文档完善前，可将它们视为进阶构件。

---

**下一篇：** [沙箱后端](backends.md)
