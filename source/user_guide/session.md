# 会话

`Session` 是 OpenRath 的状态容器。它不只是消息列表，还记录 sandbox placement 和轻量 lineage。

## 构造 Session

当前有两个常用工厂：

```python
from rath.session import Session

agent_session = Session.from_agent_prompt("You are a helpful assistant.")
user_session = Session.from_user_message("Summarize this workspace.")
```

它们分别生成一个 `system` chunk 或一个 `user` chunk。底层数据结构是：

- `ChunkKind.SYSTEM`
- `ChunkKind.USER`
- `ChunkKind.ASSISTANT`
- `ChunkKind.TOOL_RESULT`

`chunk_table_to_messages(...)` 会把这些 chunk 转为 `RathLLMMessage`，供 LLM 请求使用。

## 绑定沙箱

`run_session_loop` 会调用 `user_session.take_sandbox()`。因此进入循环前，用户侧 session 必须已经有 sandbox handle 或至少有 sandbox backend target。

```python
user_session = Session.from_user_message("List files.")
user_session = user_session.to("local")
```

如果需要指定工作目录：

```python
user_session = user_session.to("local", spec="/tmp/openrath-workspace")
```

字符串 `spec` 会被转换为 `BackendSandboxSpec(working_dir=spec)`。

也可以手动打开后绑定：

```python
from rath.backend import get
from rath.session import Session

backend = get("local")
with backend.open() as sandbox:
    user_session = Session.from_user_message("hello").with_sandbox(sandbox)
```

## sandbox 生命周期

`Session` 的 sandbox 行为是 lazy 的：

| 方法 | 行为 |
| --- | --- |
| `to(backend, spec=None)` | 关闭当前 handle，设置 backend target，返回 `self`。 |
| `require_sandbox()` | 若已有 open handle，返回它；否则按 backend target lazy open。 |
| `take_sandbox()` | 取走 handle，用于把 sandbox 从输入 session 转移到输出 session。 |
| `bind_sandbox(sandbox)` | 把已有 `BackendSandbox` 绑定到当前 session。 |
| `close_sandbox()` | 关闭当前 handle，但保留 backend target。 |

`run_session_loop` 会把用户 session 的 sandbox 转移到输出 session 上：调用后，输入 session 通常不再持有 `sandbox`，输出 session 持有同一个 handle。

## `fork` 与 `detach`

```python
forked = session.fork()
detached = session.detach()
```

两者都会复制 `chunk_table`，也都会复制 sandbox target，包括 backend 名称和 open spec，但不会复制已经打开的 sandbox handle。

差异在 lineage：

| 方法 | lineage 语义 |
| --- | --- |
| `fork()` | 新 session 的 `parent_session_ids=(source.id,)`，表示派生。 |
| `detach()` | 新 session 的 `parent_session_ids=()`，表示切成新的 lineage root。 |

模块级 `fork_session(...)` 和 `detach_session(...)` 只是调用对应方法。

## lineage 与 registry

默认 `session_graph_mode()` 为 true。框架会在这些路径写入 lineage 字段：

- `create_leaf_user(...)`
- `create_leaf_system(...)`
- `Session.fork()`
- `Session.detach()`
- `run_session_loop(...)`
- `run_session_compress(...)`

`session_registry()` 是进程内调试注册表。`run_session_loop` 会注册输入 user session、agent session 和输出 session，并把输出设置为 active。

## 压缩会话

`run_session_compress` 走一次 LLM 请求，把 `agent_session + user_session` 的消息压成新的 user-only session：

```python
from rath.session import run_session_compress

compressed = run_session_compress(
    user_session=out_session,
    agent_session=agent_session,
    agent_provider=provider,
)
```

当前实现会禁用工具：请求中 `tools=None`，默认 `tool_choice="none"`。如果模型仍返回 tool calls，会抛出 `RuntimeError`。

## 注意事项

1. 未绑定 sandbox 的 user session 不能直接进入 `run_session_loop`，否则会报 `RuntimeError("no sandbox to take")`。
2. `fork` / `detach` 不复制 open sandbox handle，这避免多个 session 意外共享一个运行时句柄。
3. `LocalBackend.close(...)` 会删除它管理的 working directory；不要把不可删除的重要目录当作长期 sandbox working directory。

**下一篇：** [沙箱后端](backends.md)
