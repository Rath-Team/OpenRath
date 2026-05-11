# Session Loop 工具调用

本教程说明 `run_session_loop(...)` 的工具调用路径：模型生成 tool call，loop 执行对应工具，再把结果写回 `tool_result` chunk，供下一轮模型请求继续使用。

## 覆盖内容
| 主题 | 结果 |
| --- | --- |
| request assembly | agent session 在前，user session 在后。 |
| tool schema | 内置工具和自定义工具会合并成模型可见 schema。 |
| tool round | assistant 先产生 tool call，loop 再执行工具并追加 `tool_result`。 |
| output session | 输出 session 继承 user-side rows，并追加新 rows。 |
| sandbox migration | 输入 session 的 sandbox handle 会迁移到输出 session。 |

## 步骤 1：准备 agent 和 user session
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

关键行：

| 行 | 解释 |
| --- | --- |
| `Session.from_agent_prompt(...)` | 创建 system chunk，作为 agent-side session。 |
| `Session.from_user_message(...)` | 创建 user chunk，作为 user-side session。 |
| `.to("local")` | 为 user session 绑定 local backend，让工具有执行位置。 |
| `flow.Provider(...)` | 保存本次请求的模型配置。 |

## 步骤 2：运行 loop
真实运行时，`run_session_loop(...)` 会使用默认 executor 发起 OpenAI-compatible 请求。测试和教程可以传入 scripted executor，让模型响应固定下来。

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

没有传入 executor 时，OpenRath 会创建 `DefaultSessionLoopExecutor`，并使用默认 OpenAI-compatible client。此时需要在环境变量或 `.env` 中配置模型网关。

## 步骤 3：理解一次工具 round
当模型返回 tool call 时，loop 会先追加 assistant row，再执行工具，再追加 tool result row：

```text
user
assistant       contains tool_calls
tool_result     contains serialized tool output
assistant       final answer or next tool_calls
```

这段顺序来自 `run_session_loop(...)`：

| 阶段 | 发生什么 |
| --- | --- |
| completion | 模型根据 messages 和 tools 返回 assistant message。 |
| assistant row | 如果有 tool call，assistant row 先进入 `rows_list`。 |
| dispatch | loop 找到同名 `FlowToolCall`，把 parsed arguments 交给工具。 |
| tool result row | 工具结果被序列化成 JSON 文本，写入 `tool_result` chunk。 |
| next completion | 下一轮请求会包含前面的 assistant row 和 tool result row。 |

## 步骤 4：观察 chunk table
```python
for row in out.chunk_table.rows:
    print(row.kind, row.payload)
```

如果模型先写文件再读文件，典型顺序会接近：

```text
user
assistant       # write_workspace_file call
tool_result     # bytes_written
assistant       # run_shell_command call
tool_result     # command stdout / stderr
assistant       # final answer
```

观察结果：

- `tool_result` row 的 `name` 会对应被调用的工具名。
- `tool_result` row 的 `content` 是模型下一轮能看到的工具输出。
- 输出 session 的开头仍然是 user-side 内容，agent system prompt 不会复制进去。

## 步骤 5：确认 sandbox 迁移
```python
sandbox = out.require_sandbox()
print(sandbox.backend.name)
```

`run_session_loop(...)` 会从输入 user session 取走 sandbox handle，并绑定到输出 session。后续继续调用另一个 agent 或 workflow 时，工具仍然可以使用同一个 sandbox。

## 常见问题
| 现象 | 检查方向 |
| --- | --- |
| 模型没有调用工具 | 检查 system prompt、user prompt、tool schema 是否足够明确。 |
| `unknown_tool` | 模型返回的工具名没有出现在 tool table。 |
| `invalid_tool_arguments` | 模型返回了无法解析的 JSON arguments。 |
| 工具执行异常 | 查看 `tool_execution_exception` 的 message 和 detail。 |
| 工具找不到 sandbox | 确认 user session 已经 `.to("local")` 或 `.with_sandbox(...)`。 |

## 练习
1. 把 user prompt 改成“只回答，不调用工具”，观察 chunk table 是否还出现 `tool_result`。
2. 给 `run_session_loop(...)` 传入一个自定义工具，确认 tool table 会包含该工具。
3. 连续运行两个 `run_session_loop(...)`，确认第二个 agent 能看到第一个 agent 留下的 `tool_result`。

## 小结

- `run_session_loop(...)` 拼接 agent/user messages 发起 completion。
- 内置工具来自 `global_system_tools()`，当前包括 `run_shell_command` 和 `write_workspace_file`。
- 工具结果会序列化成 `tool_result` chunk，供下一轮 LLM 请求使用。
- 输出 session 是后续 workflow 继续工作的核心对象。
