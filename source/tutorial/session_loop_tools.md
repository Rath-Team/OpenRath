# Session Loop 工具调用

这个教程展示 `run_session_loop` 如何把 assistant tool call 转成工具执行，并把结果写回 `tool_result` chunk。

## 步骤 1：准备 agent/user session（Step 1）

```python
from rath import flow
from rath.session import Session, run_session_loop

agent_session = Session.from_agent_prompt(
    "Use tools when the user asks for file work."
)
user_session = Session.from_user_message(
    "Create a file, then read it back."
).to("local")
provider = flow.Provider(model="gpt-5.5")
```

`agent_session` 提供 system prompt，`user_session` 提供用户输入和 backend placement。

## 步骤 2：使用 executor 运行 loop（Step 2）

默认路径会创建 `DefaultSessionLoopExecutor`。测试和 tutorial 可以传入 scripted executor，让 completion 响应可复现。

```python
out = run_session_loop(
    user_session=user_session,
    agent_session=agent_session,
    agent_provider=provider,
    executor=scripted_executor,
)
```

executor 负责两件事：

| 方法 | 作用 |
| --- | --- |
| `complete(req)` | 返回一次 chat completion 响应。 |
| `dispatch_tool(session, tool, arguments)` | 执行选中的 `FlowToolCall`。 |

## 步骤 3：观察 chunk 顺序（Step 3）

loop 会把 user rows 作为输出 session 的起点，然后追加 assistant/tool rows。

```python
for row in out.chunk_table.rows:
    print(row.kind, row.payload)
```

典型顺序：

```text
user
assistant       # contains tool_calls
tool_result     # write_workspace_file result
assistant       # contains tool_calls
tool_result     # run_shell_command result
assistant       # final answer
```

## 步骤 4：继续使用输出 session（Step 4）

`run_session_loop` 会把输入 user session 的 sandbox 移到输出 session。后续工具仍然使用同一个 active sandbox。

```python
sandbox = out.require_sandbox()
print(sandbox.backend.name)
```

## 关键结论

- `run_session_loop` 拼接 agent/user messages 发起 completion。
- 内置工具来自 `global_system_tools()`，当前包括 `run_shell_command` 和 `write_workspace_file`。
- 工具结果会序列化成 `tool_result` chunk，供下一轮 LLM 请求使用。
