# Session

`Session` 是 OpenRath 中最重要的运行时对象。一次 agent 调用、一次工具调用、一次压缩、一次多智能体交接，最终都会落到 `Session` 的变化上。

本页说明 `Session` 如何承载状态、执行位置和 lineage，以及 `fork()`、`detach()`、`run_session_loop(...)`、`run_session_compress(...)` 对 session graph 和 sandbox handle 的影响。

## 概览

`Session` 由三类状态组成：

| 层次 | 保存在哪里 | 解决的问题 |
| --- | --- | --- |
| 对话内容 | `chunk_table` | 当前 agent 能看到哪些 system/user/assistant/tool 内容。 |
| 执行位置 | `sandbox_backend`、`_sandbox_open_spec`、`sandbox` | 工具副作用发生的 backend。 |
| 状态来源 | `id`、`parent_session_ids`、`lineage_kind` | 这个 session 从哪里来，由哪个操作产生。 |

这三个层次放在同一个对象里，是因为 agent workflow 中的内容状态和执行状态会一起流动。一个 agent 生成工具调用后，后续 agent 需要读到前面的 tool result，也可能继续使用同一个 sandbox。`Session` 是这条流动链路上的传递单位。

## 源码地图

| 文件 | 负责内容 |
| --- | --- |
| `src/rath/session/session.py` | `Session` dataclass、sandbox lifecycle、`fork()`、`detach()`。 |
| `src/rath/session/chunk.py` | `ChunkKind`、`ChunkRow`、`ChunkTable` 和 message 转换。 |
| `src/rath/session/loop.py` | `run_session_loop(...)`、tool dispatch、`tool_result` 写回。 |
| `src/rath/session/compress.py` | `run_session_compress(...)`。 |
| `src/rath/session/graph/recording.py` | `LineageRecorder` 与 lineage mode。 |
| `src/rath/session/graph/traverse.py` | graph 遍历与 acyclic validation。 |

## 为什么用表组织上下文

`Session.chunk_table` 是按时间顺序排列的 `ChunkRow` tuple。每一行都有 `kind` 和 `payload`。这比直接保存一段字符串更适合 agent runtime，因为工具调用需要保留结构化信息。

| Chunk kind | Payload 重点 | 产生位置 | 转成 LLM message 后 |
| --- | --- | --- | --- |
| `system` | `content` | `Session.from_agent_prompt(...)` | `role="system"` |
| `user` | `content` | `Session.from_user_message(...)` | `role="user"` |
| `assistant` | `content`、`tool_calls` | `run_session_loop(...)` | `role="assistant"` |
| `tool_result` | `tool_call_id`、`name`、`content` | 工具执行后 | `role="tool"` |

关键行为在 `chunk_table_to_messages(...)`：

```python
from rath.session import Session
from rath.session.chunk import chunk_table_to_messages

user = Session.from_user_message("List files.")
messages = chunk_table_to_messages(user.chunk_table)
print(messages[0].role)
print(messages[0].content)
```

这一层的核心约束是：OpenRath 保存的是可回放的 transcript。`assistant` 行中的 `tool_calls` 和 `tool_result` 行中的 `tool_call_id` 会在下一轮 LLM 请求中重新拼成 OpenAI-compatible messages，使模型可以读到“我刚刚调用了什么工具，工具返回了什么”。

## Agent session 与 user session

OpenRath 把 system prompt 放在 agent-side session，把用户输入和运行结果放在 user-side session。

| Session | 常见内容 | 生命周期 |
| --- | --- | --- |
| agent session | `system` chunk | 由 `AgentParam` 或 `flow.Agent` 持有，通常长期复用。 |
| user session | `user`、`assistant`、`tool_result` chunks | 随着 workflow 调用不断产生新 session。 |

`run_session_loop(...)` 构造请求时，会把 agent session 的 messages 放在 user session 的 messages 前面：

```text
request messages = agent_session rows + user_session rows
```

输出 session 只从 user-side rows 开始，再追加 assistant/tool rows。system prompt 不会被复制进输出 session。这让 agent 配置和用户运行状态保持分离：换一个 agent session，就可以用同一份 user session 进入另一段行为。

## Session graph

每个 `Session` 都有一个 `id`。当某个操作产生新 session 时，OpenRath 会把来源写到 lineage 字段里。

| 字段 | 含义 |
| --- | --- |
| `id` | 当前 session 的 UUID。 |
| `parent_session_ids` | 产生当前 session 的父 session。 |
| `lineage_operator` | 产生当前 session 的操作名称。 |
| `lineage_kind` | 操作类别，例如 fork、detach、loop、compress。 |
| `lineage_extras` | 额外结构化信息。 |

这个 graph 的用途是解释运行过程。多 agent workflow 里，多个 agent 会依次接收上一个 agent 的输出 session；nested workflow 里，子 workflow 也只是继续接收和返回 session。只要每个操作都把 parent 写清楚，就可以追踪最终结果由哪些步骤组成。

## 五个原语

OpenRath 当前可以用五个原语理解 `Session` 的变化。

| 原语 | 代码入口 | 内容行为 | Graph 行为 | Sandbox 行为 |
| --- | --- | --- | --- | --- |
| create | `Session.from_user_message(...)`、`Session.from_agent_prompt(...)` | 创建单行 transcript。 | classmethod 默认 `UNKNOWN`；`create_leaf_user(...)` 和 `create_leaf_system(...)` 会写 leaf lineage。 | 没有 sandbox target。 |
| fork | `session.fork()`、`fork_session(session)` | 复制 chunk rows。 | parent 指向源 session，`lineage_kind=OP_FORK`。 | 复制 backend target，不复制 open handle。 |
| detach | `session.detach()`、`detach_session(session)` | 复制 chunk rows。 | parent 为空，`lineage_kind=OP_DETACH`。 | 复制 backend target，不复制 open handle。 |
| loop | `run_session_loop(user_session, agent_session, ...)` | 复制 user rows，追加 assistant/tool rows。 | parents 是 user session 和 agent session。 | 从输入 user session 取走 sandbox，绑定到输出 session。 |
| compress | `run_session_compress(user_session, agent_session, ...)` | 把模型返回的摘要写成新的 user row。 | parents 是 user session 和 agent session，并记录 lossy compression。 | 从输入 user session 取走 sandbox，绑定到输出 session。 |

### 什么时候用 fork

`fork()` 适合从同一个状态派生多个后续方向。例如同一份用户需求可以交给两个不同 workflow 尝试。fork 后的新 session 保留 parent，因此 graph 能说明它来自原始状态。

### 什么时候用 detach

`detach()` 适合把 transcript 复制出来当作新的起点。它保留内容和 backend target，但 graph parent 为空。这个操作适合手动切断 lineage，例如把中间状态导出为新任务入口。

### 什么时候用 compress

`run_session_compress(...)` 适合把长 transcript 压成一个新的 user-side 摘要。它会关闭 tool 使用路径，要求模型只返回文本。当前实现中，如果模型返回 tool calls，会直接抛 `RuntimeError`。

## Sandbox 生命周期

`Session` 同时保存 sandbox target 和 open handle。

| 字段 | 含义 |
| --- | --- |
| `sandbox_backend` | backend 名称，例如 `local` 或 `opensandbox`。 |
| `_sandbox_open_spec` | 打开 backend 时使用的 spec；字符串 spec 会转成 `BackendSandboxSpec(working_dir=...)`。 |
| `sandbox` | 已打开的 `BackendSandbox` handle。 |

常用方法：

| 方法 | 行为 |
| --- | --- |
| `to("local", spec=...)` | 关闭当前 handle，设置 backend target，返回同一个 session。 |
| `with_sandbox(sandbox)` | 绑定已经打开的 sandbox handle。 |
| `require_sandbox()` | 返回当前 handle；如果只有 backend target，则 lazy open。 |
| `take_sandbox()` | 取走当前 handle；如果只有 backend target，则 lazy open 后取走。 |
| `close_sandbox()` | 关闭当前 handle，保留 backend target。 |

`fork()` 与 sandbox 的关系容易混淆：fork 会复制 backend target，让派生 session 知道将来打开哪个 backend；已经打开的 handle 仍留在源 session 上。

```python
from rath.session import Session

source = Session.from_user_message("Inspect project.").to("local")
forked = source.fork()

print(source.sandbox is None)
print(forked.sandbox is None)
print(forked.sandbox_backend)
```

## run_session_loop 的状态迁移

`run_session_loop(...)` 做四件事：

1. 合并内置工具和用户传入的 `FlowToolCall`。
2. 从输入 user session 取走 sandbox，并创建输出 session。
3. 循环发起 LLM completion；如果 assistant 返回 tool calls，就执行工具并追加 `tool_result`。
4. 没有 tool calls 时追加最终 assistant row，并返回输出 session。

状态迁移可以用表描述：

| 位置 | loop 前 | loop 后 |
| --- | --- | --- |
| 输入 user session | 持有原始 user rows，可能持有 sandbox。 | sandbox 被取走，`user_session.sandbox` 变成 `None`。 |
| agent session | 持有 system rows。 | 不变。 |
| 输出 session | 不存在。 | 持有 user rows、assistant rows、tool result rows，并接管 sandbox。 |

工具异常不会直接中断 loop。当前实现会把错误写成 JSON `tool_result`，再把这个结果交回模型继续处理。包括三类情况：

| 情况 | 写入的 error kind |
| --- | --- |
| tool arguments 不是可解析 JSON | `invalid_tool_arguments` |
| 模型请求了不存在的工具 | `unknown_tool` |
| 工具执行抛异常 | `tool_execution_exception` |

## run_session_compress 的状态迁移

`run_session_compress(...)` 使用同样的 agent/user session 拼接方式，但它创建的是一个新的 user-only session。

| 行为 | 当前实现 |
| --- | --- |
| 请求内容 | agent session rows + user session rows + 压缩指令。 |
| tool choice | 强制禁用工具。 |
| 输出内容 | 模型文本会成为唯一 `user` chunk。 |
| sandbox | 从输入 user session 迁移到输出 session。 |
| lineage extras | `compression.lossy=True`、`compression.rows_out=1`。 |

这个操作是有损的。它适合降低上下文长度，也意味着压缩后的 session 只保留模型写出的摘要文本。

## 读代码时的检查点

| 想确认的问题 | 看哪里 |
| --- | --- |
| row 如何变成 LLM message | `src/rath/session/chunk.py::chunk_table_to_messages` |
| sandbox 何时 lazy open | `src/rath/session/session.py::_ensure_sandbox` |
| loop 如何迁移 sandbox | `src/rath/session/loop.py::run_session_loop` 中的 `take_sandbox()` |
| compress 如何禁用工具 | `src/rath/session/compress.py::run_session_compress` 中的 `default_tool_choice="none"` |
| fork/detach 是否复制 open handle | `tests/session/test_session_fork_detach_merge.py` |

## 边界条件

| 行为 | 当前实现 |
| --- | --- |
| 无 backend target 时调用 `take_sandbox()` | 抛 `RuntimeError("no sandbox to take")`。 |
| 无 backend target 时调用 `require_sandbox()` | 抛 `RuntimeError`，提示调用 `session.to("local")` 或 `bind_sandbox(...)`。 |
| 已绑定 closed sandbox 后调用 `require_sandbox()` | 抛 `RuntimeError("session sandbox is closed")`。 |
| `fork()` / `detach()` | 复制 chunk rows 和 sandbox target，保留源 session 的 open handle。 |
| `run_session_loop(...)` | 输出 session 接管输入 user session 的 sandbox handle。 |
| malformed tool arguments | 写入 JSON error `tool_result`，loop 继续。 |
| unknown tool | 写入 JSON error `tool_result`，loop 继续。 |
| tool exception | 捕获异常并写入 JSON error `tool_result`。 |
| compress tool calls | `run_session_compress(...)` 抛 `RuntimeError`。 |

## 测试覆盖

| 行为 | 测试 |
| --- | --- |
| chunk to messages | `tests/session/test_chunk_messages.py` |
| sandbox lifecycle | `tests/session/test_session_sandbox_behavior.py` |
| fork/detach primitives | `tests/session/test_session_primitives.py`, `tests/session/test_session_fork_detach_merge.py` |
| loop with local backend | `tests/session/test_run_session_loop_local.py` |
| loop edge cases | `tests/session/test_run_session_loop_edges.py` |
| lineage graph | `tests/session/test_lineage_graph_unit.py` |
| live loop/compress | `tests/integration/test_session_loop_real.py`, `tests/integration/test_session_compress_real.py` |
