(pkg-session)=
# `rath.session`

会话状态、chunk transcript、session loop、上下文压缩和 lineage graph。

## 源码
| 模块 | 源码 |
| --- | --- |
| `rath.session.session` | `src/rath/session/session.py` |
| `rath.session.chunk` | `src/rath/session/chunk.py` |
| `rath.session.loop` | `src/rath/session/loop.py` |
| `rath.session.compress` | `src/rath/session/compress.py` |
| `rath.session.primitives` | `src/rath/session/primitives.py` |
| `rath.session.graph` | `src/rath/session/graph/` |
| `rath.session.manager` | `src/rath/session/manager.py` |

## 公共契约
### `Session`

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `chunk_table` | `ChunkTable` | chronological chunk rows。 |
| `id` | `UUID` | session identity。 |
| `sandbox` | `BackendSandbox` \| `None` | 当前打开的 sandbox handle。 |
| `sandbox_backend` | `str` \| `None` | lazy open 使用的 backend name。 |
| `parent_session_ids` | `tuple[UUID, ...]` | lineage parents。 |
| `lineage_operator` | `str` | 产生当前 session 的操作。 |
| `lineage_kind` | `LineageKind` | lineage 操作类别。 |

| 方法 | 返回 | 行为 |
| --- | --- | --- |
| `Session.from_agent_prompt(prompt)` | `Session` | 创建单个 `system` chunk。 |
| `Session.from_user_message(text)` | `Session` | 创建单个 `user` chunk。 |
| `session.to(backend="local", spec=None)` | `Session` | 设置 sandbox target，关闭当前 handle。 |
| `session.require_sandbox()` | `BackendSandbox` | 返回或 lazy open 当前 sandbox。 |
| `session.take_sandbox()` | `BackendSandbox` | 取走 handle，供 loop 绑定到输出 session。 |
| `session.fork()` | `Session` | 复制 chunk rows 与 sandbox target，parent 指向源 session。 |
| `session.detach()` | `Session` | 复制 chunk rows 与 sandbox target，创建新的 lineage root。 |

### Chunk 辅助函数
| 函数 | 返回 | 用途 |
| --- | --- | --- |
| `user_text_chunk(text)` | `ChunkRow` | 创建 user row。 |
| `system_text_chunk(text)` | `ChunkRow` | 创建 system row。 |
| `assistant_turn_chunk(tool_calls, content=None)` | `ChunkRow` | 创建 assistant row。 |
| `tool_feedback_chunk(tool_call_id, name, body)` | `ChunkRow` | 创建 tool result row。 |
| `chunk_table_to_messages(tab)` | `tuple[RathLLMMessage, ...]` | 转成 chat completion messages。 |

### 循环
```python
run_session_loop(
    user_session: Session,
    agent_session: Session,
    *,
    agent_provider: Provider,
    tools: list[FlowToolCall] | None = None,
    executor: SessionLoopExecutor | None = None,
    max_tool_rounds: int = 16,
) -> Session
```

| 参数 | 说明 |
| --- | --- |
| `user_session` | user-side transcript 和 sandbox placement。 |
| `agent_session` | agent/system transcript，参与 request assembly。 |
| `agent_provider` | model 和 request 参数。 |
| `tools` | 额外 `FlowToolCall` 实例。 |
| `executor` | completion/tool dispatch 替换点。 |
| `max_tool_rounds` | tool-call round 上限。 |

返回的 `Session` 以 user rows 为起点，追加 assistant rows 和 `tool_result` rows。输出 session 的 lineage parents 是 user session 和 agent session。

### 压缩
```python
run_session_compress(
    user_session: Session,
    agent_session: Session,
    *,
    agent_provider: Provider,
    executor: SessionLoopExecutor | None = None,
    compress_instruction: str | None = None,
    register_sessions: bool = True,
) -> Session
```

返回 user-only session。compress request 使用 `tools=None` 和 `tool_choice="none"`；模型返回 tool calls 时抛 `RuntimeError`。

### 异常与边界行为
| 位置 | 行为 |
| --- | --- |
| `Session.require_sandbox()` | 无 backend target 时抛 `RuntimeError`。 |
| `Session.take_sandbox()` | 无 sandbox 且无 backend target 时抛 `RuntimeError`。 |
| `run_session_loop(...)` | tool arguments 非 JSON、未知工具、工具执行异常会写入 JSON error `tool_result`。 |
| `run_session_compress(...)` | 空模型内容、tool calls、异常 finish reason 会抛 `RuntimeError`。 |

## 自动文档
```{eval-rst}
.. autoclass:: rath.session.Session
   :members:

.. autoclass:: rath.session.ChunkRow
   :members:

.. autoclass:: rath.session.ChunkTable
   :members:

.. autofunction:: rath.session.run_session_loop

.. autoclass:: rath.session.SessionLoopExecutor
   :members:

.. autofunction:: rath.session.run_session_compress

.. autofunction:: rath.session.create_leaf_user

.. autofunction:: rath.session.create_leaf_system

.. autofunction:: rath.session.fork_session

.. autofunction:: rath.session.detach_session
```

[← API Reference](index.md)
