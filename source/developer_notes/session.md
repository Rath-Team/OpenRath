# 会话（Session）

`Session` 是 OpenRath workflow 中流动的运行时状态对象。它承载 chunk transcript、backend placement 和 lineage metadata。

本页回答：运行状态如何流动，`fork()`、`detach()`、`run_session_loop(...)` 和 `run_session_compress(...)` 如何改变 session graph，以及 sandbox handle 何时迁移。

## 源码地图（Source Map）

| 文件 | 负责内容 |
| --- | --- |
| `src/rath/session/session.py` | `Session` dataclass、sandbox lifecycle、`fork()`、`detach()`。 |
| `src/rath/session/chunk.py` | `ChunkKind`、`ChunkRow`、`ChunkTable` 和 message 转换。 |
| `src/rath/session/loop.py` | `run_session_loop(...)`、tool dispatch、`tool_result` 写回。 |
| `src/rath/session/compress.py` | `run_session_compress(...)`。 |
| `src/rath/session/graph/recording.py` | `LineageRecorder` 与 lineage mode。 |
| `src/rath/session/graph/traverse.py` | graph 遍历与 acyclic validation。 |

## 表格化上下文（Context As A Table）

`Session.chunk_table` 是按时间顺序排列的 `ChunkRow` 表。每一行都有 `kind` 和 `payload`。

| Chunk kind | Payload 重点 | 产生位置 |
| --- | --- | --- |
| `system` | `content` | `Session.from_agent_prompt(...)` |
| `user` | `content` | `Session.from_user_message(...)` |
| `assistant` | `content`、`tool_calls` | `run_session_loop(...)` |
| `tool_result` | `tool_call_id`、`name`、`content` | `run_session_loop(...)` 工具执行后 |

```python
from rath.session import Session

user = Session.from_user_message("List files.")
for row in user.chunk_table.rows:
    print(row.kind, row.payload)
```

`chunk_table_to_messages(...)` 会把这些 rows 转成 chat completion messages。agent session 的 system rows 会在 request 中放到 user rows 前面。

## 会话图（Session Graph）

OpenRath 使用 session 自身的 lineage 字段表达 graph。

| 字段 | 含义 |
| --- | --- |
| `id` | 当前 session 的 UUID。 |
| `parent_session_ids` | 产生当前 session 的父 session。 |
| `lineage_operator` | 产生当前 session 的操作名称。 |
| `lineage_kind` | 操作类别，例如 fork、detach、loop、compress。 |
| `lineage_extras` | 额外结构化信息。 |

这些字段由 `LineageRecorder` 写入。`session_registry()` 提供进程内调试注册表，`ancestors_bfs(...)`、`validate_acyclic(...)` 等 helper 可以遍历和检查 graph。

## 五个原语（Five Primitives）

| Primitive | 代码入口 | Graph 行为 |
| --- | --- | --- |
| create | `Session.from_user_message(...)`、`Session.from_agent_prompt(...)`、`create_leaf_user(...)`、`create_leaf_system(...)` | classmethod 创建基础 transcript；leaf helper 会记录 leaf lineage。 |
| fork | `session.fork()`、`fork_session(session)` | 新 session 的 `parent_session_ids=(source.id,)`，`lineage_kind=OP_FORK`。 |
| detach | `session.detach()`、`detach_session(session)` | 新 session 的 `parent_session_ids=()`，`lineage_kind=OP_DETACH`。 |
| loop | `run_session_loop(user_session, agent_session, ...)` | 输出 session 的 parents 是 user session 与 agent session，`lineage_kind=OP_SESSION_LOOP`。 |
| compress | `run_session_compress(user_session, agent_session, ...)` | 输出 user-only session，parents 是 user session 与 agent session，`lineage_kind=OP_SESSION_COMPRESS`。 |

## 沙箱绑定（Sandbox Placement）

`Session` 记录 sandbox target 和可选 open handle。

| 方法 | 行为 |
| --- | --- |
| `to("local", spec=...)` | 设置 backend target，关闭当前 handle，返回同一个 session。 |
| `with_sandbox(sandbox)` | 绑定已经打开的 sandbox handle。 |
| `require_sandbox()` | 返回当前 handle，或按 backend target lazy open。 |
| `take_sandbox()` | 取走当前 handle，用于把 sandbox 转移到输出 session。 |
| `close_sandbox()` | 关闭当前 handle，保留 backend target。 |

`run_session_loop(...)` 会从输入 user session 取走 sandbox，并把它绑定到输出 session。`fork()` 和 `detach()` 会复制 sandbox target，不复制已经打开的 handle。

## 调用路径（Call Path）

一次 tool-using loop 的主要调用路径：

```text
run_session_loop
  -> merge_tools_for_loop
  -> user_session.take_sandbox
  -> chunk_table_to_messages(agent_session)
  -> chunk_table_to_messages(user rows)
  -> provider_into_chat_request
  -> executor.complete
  -> executor.dispatch_tool
  -> tool_feedback_chunk
  -> LineageRecorder.stamp_new_session
```

`run_session_compress(...)` 的路径更短：

```text
run_session_compress
  -> chunk_table_to_messages(agent_session + user_session)
  -> provider_into_chat_request(tools=None, tool_choice="none")
  -> executor.complete
  -> user_text_chunk(model_content)
  -> LineageRecorder.stamp_new_session
```

## 边界条件（Boundary Conditions）

| 行为 | 当前实现 |
| --- | --- |
| `fork()` / `detach()` | 复制 chunk rows 和 sandbox target，保留源 session 的 open handle。 |
| `run_session_loop(...)` | 输出 session 接管输入 user session 的 sandbox handle。 |
| malformed tool arguments | 写入 JSON error `tool_result`，loop 继续。 |
| unknown tool | 写入 JSON error `tool_result`，loop 继续。 |
| tool exception | 捕获异常并写入 JSON error `tool_result`。 |
| compress tool calls | `run_session_compress(...)` 抛 `RuntimeError`。 |

## 测试覆盖（Test Coverage）

| 行为 | 测试 |
| --- | --- |
| chunk to messages | `tests/session/test_chunk_messages.py` |
| sandbox lifecycle | `tests/session/test_session_sandbox_behavior.py` |
| fork/detach primitives | `tests/session/test_session_primitives.py`, `tests/session/test_session_fork_detach_merge.py` |
| loop with local backend | `tests/session/test_run_session_loop_local.py` |
| loop edge cases | `tests/session/test_run_session_loop_edges.py` |
| lineage graph | `tests/session/test_lineage_graph_unit.py` |
| live loop/compress | `tests/integration/test_session_loop_real.py`, `tests/integration/test_session_compress_real.py` |
