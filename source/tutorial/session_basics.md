# Session 基础

本教程说明 `Session` 的基础结构：它保存对话内容、工具执行位置和 lineage 信息。完成这些步骤后，可以判断一个 session 当前包含哪些上下文、工具会在哪个 backend 执行，以及它与其他 session 的 graph 关系。

## 覆盖内容

| 主题 | 结果 |
| --- | --- |
| 创建 agent/user session | system prompt 和 user message 会成为不同类型的 chunk。 |
| 读取 chunk table | `chunk_table.rows` 是按时间排序的结构化记录。 |
| 使用 fork 与 detach | 二者都会复制 transcript，但 graph 关系不同。 |
| 设置 backend target | `to("local")` 只设置目标，sandbox handle 会按需打开。 |
| 理解 handle 生命周期 | context manager 退出后，当前 handle 会被关闭。 |

## 步骤 1：创建 agent 和 user session

先创建两个 session：一个代表 agent 的 system prompt，一个代表用户输入。

```python
from rath.session import Session

agent = Session.from_agent_prompt("You are a concise assistant.")
user = Session.from_user_message("List files in the sandbox.")

print(agent.chunk_table.rows[-1].kind)
print(user.chunk_table.rows[-1].kind)
print(user.chunk_table.rows[-1].payload["content"])
```

关键行解释：

| 代码 | 作用 |
| --- | --- |
| `Session.from_agent_prompt(...)` | 创建包含 `system` chunk 的 session。 |
| `Session.from_user_message(...)` | 创建包含 `user` chunk 的 session。 |
| `chunk_table.rows[-1]` | 读取最新一条 chunk。 |

输出应接近：

```text
system
user
List files in the sandbox.
```

此时两个 session 都还没有 sandbox target。它们只保存 transcript。

## 步骤 2：理解 chunk table

`Session` 不把上下文保存成一整段字符串，而是保存成一张按时间排序的表。这样 assistant tool call 和 tool result 可以保留结构。

```python
for index, row in enumerate(user.chunk_table.rows):
    print(index, row.kind, row.payload)
```

对刚创建的 user session 来说，输出里只有一行：

```text
0 user {'content': 'List files in the sandbox.'}
```

后续 `run_session_loop(...)` 会在这张表后面追加 assistant row 和 tool result row。也就是说，agent 每一步行动都会成为 session history 的一部分。

## 步骤 3：fork 保留来源

`fork()` 适合从当前状态派生一个新分支。它会复制 chunk rows，并把源 session 记录为 parent。

```python
forked = user.fork()

print(forked.chunk_table.rows == user.chunk_table.rows)
print(forked.parent_session_ids == (user.id,))
print(forked.lineage_operator)
```

输出应接近：

```text
True
True
Session.fork
```

关键点：

| 字段 | fork 后的含义 |
| --- | --- |
| `chunk_table.rows` | 和源 session 内容相同。 |
| `parent_session_ids` | 指向源 session。 |
| `lineage_operator` | 当前实现写入 `Session.fork`。 |

fork 常用于分支探索。例如同一份用户需求可以交给两个 workflow 分别处理，之后通过 graph 知道它们来自同一个输入。

## 步骤 4：detach 创建新的起点

`detach()` 也会复制 transcript，但它会让新 session 成为新的 lineage root。

```python
detached = forked.detach()

print(detached.chunk_table.rows == forked.chunk_table.rows)
print(detached.parent_session_ids)
print(detached.lineage_operator)
```

输出应接近：

```text
True
()
Session.detach
```

detach 适合把某个中间状态复制成新的任务入口。内容保留，graph parent 清空。

## 步骤 5：设置 local backend target

`to("local")` 设置这个 session 将来使用哪个 backend。它返回同一个 session，因此可以链式调用。

```python
user.to("local")

print(user.sandbox_backend)
print(user.sandbox is None)
```

输出应接近：

```text
local
True
```

`to("local")` 设置的是 backend target，不会立刻打开 sandbox handle。handle 会在 `require_sandbox()`、`take_sandbox()` 或 `with session:` 中按需打开。

## 步骤 6：打开并关闭 sandbox handle

使用 context manager 可以让 session 在进入时打开 sandbox，在退出时关闭当前 handle。

```python
with user:
    sandbox = user.require_sandbox()
    print(sandbox.backend.name)
    print(user.sandbox is sandbox)
    print(sandbox.closed)

print(user.sandbox is None)
print(sandbox.closed)
```

输出应接近：

```text
local
True
False
True
True
```

关键行解释：

| 代码 | 作用 |
| --- | --- |
| `with user:` | 进入时调用 `_ensure_sandbox()`，退出时调用 `close_sandbox()`。 |
| `require_sandbox()` | 返回当前 handle；没有 handle 但有 backend target 时会 lazy open。 |
| `sandbox.closed` | local backend 关闭后会标记为 closed。 |

## 步骤 7：fork 不复制 open handle

如果源 session 已经打开 sandbox，fork 出来的 session 会复制 backend target，但不会共享同一个 open handle。

```python
source = Session.from_user_message("inspect").to("local")

with source:
    source_sandbox = source.require_sandbox()
    forked = source.fork()

    print(source.sandbox is source_sandbox)
    print(forked.sandbox is None)
    print(forked.sandbox_backend)
```

输出应接近：

```text
True
True
local
```

open sandbox handle 有生命周期和副作用边界。`fork()` 只复制“将来打开哪个 backend”的 target，不复制已经打开的 handle。

## 常见问题

| 现象 | 原因 | 检查方式 |
| --- | --- | --- |
| `RuntimeError: no sandbox to take` | session 没有 backend target，也没有 handle。 | 先调用 `session.to("local")` 或 `with_sandbox(...)`。 |
| `session sandbox is closed` | session 绑定了一个已经关闭的 handle。 | 重新调用 `to(...)` 或绑定新的 sandbox。 |
| local workspace 不见了 | `LocalBackend.close(...)` 会清理它管理的目录。 | 不把不可重建的重要目录作为 local sandbox workspace。 |
| fork 后没有 `sandbox` | 当前设计只复制 backend target。 | 查看 `forked.sandbox_backend`。 |

## 练习

1. 把 `user.to("local")` 改成 `user.to("local", spec=".")`，观察 sandbox handle 对应的目录。
2. 对同一个 `user` 连续调用两次 `fork()`，打印每个 fork 的 `parent_session_ids`。
3. 在 `with user:` 内写入一个文件，再退出 context，观察 local backend 关闭后的 workspace 行为。

## 小结

- `Session` 同时承载 transcript、backend target 和 lineage。
- `chunk_table` 是结构化上下文表，后续 tool call 和 tool result 都会追加进去。
- `fork()` 复制内容并保留 parent；`detach()` 复制内容并创建新的 graph root。
- `to(...)` 设置执行位置；sandbox handle 会按需打开。
- `run_session_loop(...)` 会把输入 user session 的 sandbox 迁移到输出 session，这一点会在后续教程展开。
