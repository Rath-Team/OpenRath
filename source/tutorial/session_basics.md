# Session 基础

这个教程展示 `Session` 的三个基本行为：创建 chunk transcript、派生会话，以及绑定 sandbox target。

## 步骤 1：创建 agent/user session（Step 1）

`Session.from_agent_prompt(...)` 创建 system chunk，`Session.from_user_message(...)` 创建 user chunk。

```python
from rath.session import Session

agent = Session.from_agent_prompt("You are a concise assistant.")
user = Session.from_user_message("List files in the sandbox.")

print(agent.chunk_table.rows[-1].kind)
print(user.chunk_table.rows[-1].payload["content"])
```

此时 `agent` 和 `user` 都只包含 transcript。sandbox 相关字段仍然为空。

## 步骤 2：fork 与 detach（Step 2）

`fork()` 复制 transcript 和 sandbox target，并把源 session 记录为 parent。`detach()` 复制 transcript 和 sandbox target，并创建新的 lineage root。

```python
forked = user.fork()
detached = forked.detach()

print(forked.parent_session_ids)
print(detached.parent_session_ids)
print(forked.lineage_operator)
print(detached.lineage_operator)
```

这两个操作都会复制 chunk rows。已经打开的 sandbox handle 会留在源 session 上，派生出的 session 会在需要时重新打开自己的 handle。

## 步骤 3：绑定 local backend（Step 3）

`to("local")` 设置 backend target。sandbox handle 会在 `require_sandbox()`、`take_sandbox()` 或进入 `with session:` 时打开。

```python
user.to("local")

with user:
    sandbox = user.require_sandbox()
    print(sandbox.backend.name)
    print(sandbox.handle)
```

退出 context 后，`Session.close_sandbox()` 会关闭当前 handle。`LocalBackend` 会清理它管理的工作目录。

## 关键结论

- `Session` 承载 transcript、backend placement 和 lineage。
- `fork()` 与 `detach()` 复制 chunk rows 和 sandbox target。
- `to(...)` 只设置执行位置，sandbox handle 在实际使用时打开。
