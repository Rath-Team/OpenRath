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

`run_session_loop` 会与用户 session 共享同一个 sandbox（引用计数 +1），所以进入循环前 user session 至少要有 sandbox handle 或 backend target。

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
    user_session = Session.from_user_message("hello").bind_sandbox(sandbox)
```

## sandbox 生命周期

`Session.sandbox` 走**引用计数**：每个持有该 sandbox 的 session 算 1 个引用，`close_sandbox()` 释放一次，归零时 backend 才真正关闭。

| 方法 | 行为 |
| --- | --- |
| `to(backend, spec=None)` | 释放当前 handle，设置 backend target，返回 `self`。 |
| `require_sandbox()` | 若已有 open handle，返回它；否则按 backend target lazy open 并获取一个引用。 |
| `bind_sandbox(sandbox)` | 释放旧 handle，对新 sandbox 获取一个引用（refcount +1）。 |
| `close_sandbox()` | 释放当前引用；引用计数为 0 时 backend 才 close。 |

`run_session_loop` / `run_session_compress` 把用户 session 的 sandbox 共享给输出 session（refcount +1）。两边的 session 持有同一个 handle，都可以独立 `close_sandbox()`；只有最后一个引用释放后，backend 才真正回收。

## `fork`、`detach`、`merge`

```python
forked = session.fork()
detached = session.detach()
merged = session.merge(other)
```

三者都会复制 `chunk_table`，并与源 session **共享同一个 sandbox 引用**（refcount +1）。

差异在 lineage 与适用语义：

| 方法 | lineage 语义 | 备注 |
| --- | --- | --- |
| `fork()` | 新 session `parent_session_ids=(source.id,)` | 表示并行派生。 |
| `detach()` | 新 session `parent_session_ids=()` | 切成新的 lineage root，但 sandbox 仍共享。 |
| `merge(other)` | `parent_session_ids=(self.id, other.id)` | 拼接 `self.rows + other.rows`；两个 session 必须引用同一个 sandbox（按 `is` 判断），否则抛 `ValueError`。`cumulative_usage` 自动相加。 |

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

1. 未绑定 sandbox 的 user session 仍可以进入 `run_session_loop`，但工具调用时会拿不到 sandbox 而失败；交互式场景请先 `to(...)` 或 `bind_sandbox(...)`。
2. `fork` / `detach` / `merge` 都与源 session 共享 sandbox 引用——多个 session 看到的是同一个工作目录或远端容器。若希望各自独立运行时句柄，可先 `close_sandbox()` 再 `to(...)` 重开一个。
3. `LocalBackend.close(...)` 仅在它自己 `mkdtemp` 出来的 working directory 上调 `rmtree`；用户通过 `spec.working_dir` 显式指定的目录会保留。

**下一篇：** [沙箱后端](backends.md)
