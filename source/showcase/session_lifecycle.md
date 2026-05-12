# Session 生命周期讲解

`Session` 是 OpenRath 最值得讲清楚的对象。它既是对话历史，也是 sandbox placement，也是 lineage 节点。

## 生命周期步骤

### 1. 创建

```python
session = Session.from_user_message("Summarize this directory.")
```

这一步只创建 chunk，不打开 sandbox。

### 2. 绑定运行目标

```python
session = session.to("local")
```

这一步设置 `sandbox_backend="local"`。sandbox handle 仍然是 lazy 的，真正需要时才打开。

### 3. 进入 loop

```python
out = run_session_loop(
    user_session=session,
    agent_session=agent_session,
    agent_provider=provider,
)
```

loop 会取走用户 session 的 sandbox，并绑定到输出 session。这让“当前有效状态”始终在最新 session 上。

### 4. 工具结果进入 chunk

当模型调用工具，输出 session 会追加两类 chunk：

- assistant chunk：记录 tool calls；
- tool_result chunk：记录工具返回值的 JSON 文本。

### 5. 派生或压缩

`fork()` 保留父节点关系；`detach()` 切成新的 lineage root；`run_session_compress()` 用 LLM 把历史压成一个新的 user-only session。

## 展示重点

展示时建议直接打印 `Session.__repr__`。它会像 PyTorch tensor 一样对长 chunk 做省略，适合让听众看到 Session 是可观察的结构化对象，而不是不可见的 prompt 拼接。

## 常见误解

| 误解 | 正确说法 |
| --- | --- |
| Session 就是 messages list | Session 还包含 sandbox placement 和 lineage。 |
| fork 会复制 sandbox | fork 只复制 backend target，不复制 open handle。 |
| loop 修改原 session | loop 返回新 session，并把 sandbox 转到输出上。 |
| compress 是本地摘要 | compress 是一次 LLM 请求，且禁用工具。 |
