# 工具（Tool）

OpenRath 的 tool 系统分成两层：model-facing `FlowToolCall` 和 backend-facing `BackendTool*` payload。

本页回答：模型生成的 tool call 如何进入 executor，`FlowToolCall` 如何同时提供 schema 和 runtime 行为，`tool_result` 如何写回 session。

## 源码地图（Source Map）

| 文件 | 负责内容 |
| --- | --- |
| `src/rath/flow/tool/base.py` | `FlowToolCall` abstract base class。 |
| `src/rath/flow/tool/system_tool.py` | built-in tools 和 backend payload factories。 |
| `src/rath/flow/tool/tool_table.py` | tool merge、schema conversion、name conflict。 |
| `src/rath/session/loop.py` | tool call dispatch、tool result serialization。 |
| `src/rath/backend/tool_types.py` | backend-facing payload dataclasses。 |

## 工具接口（FlowToolCall）

`FlowToolCall` 是 session loop 使用的工具接口。

```python
from rath.flow.tool import FlowToolCall


class MyTool(FlowToolCall):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}, "additionalProperties": False}

    def __call__(self, session, arguments):
        return {"ok": True}
```

| 属性/方法 | 作用 |
| --- | --- |
| `name` | LLM tool schema 中的 function name。 |
| `description` | 可选说明，帮助模型选择工具。 |
| `parameters` | JSON Schema object。 |
| `__call__(session, arguments)` | runtime 执行入口。 |

内置工具来自 `global_system_tools()`，当前包括：

| Tool | Backend payload |
| --- | --- |
| `run_shell_command` | `BackendToolCommandRun` |
| `write_workspace_file` | `BackendToolFilesWrite` |

## Session Loop 中的工具调用（Tool Call In Session Loop）

`run_session_loop(...)` 的工具路径：

| 阶段 | 行为 |
| --- | --- |
| merge | `merge_tools_for_loop(tools)` 合并内置工具和用户工具。 |
| schema | `tools_dict_to_schemas(...)` 把工具转成 OpenAI-style tool schema。 |
| completion | LLM response 返回 assistant message 和 `tool_calls`。 |
| dispatch | executor 调用 `dispatch_tool(out, flow_tool, arguments)`。 |
| feedback | 结果被序列化成 `tool_result` chunk。 |
| lineage | loop 输出 session 记录 `OP_SESSION_LOOP` lineage。 |

工具名与内置工具名冲突时，`merge_tools_for_loop(...)` 会抛 `ToolNameConflictError`。

## 后端载荷（Backend Payloads）

Backend payload 位于 `rath.backend.tool_types`。它们描述后端侧操作。

| Payload | 用途 |
| --- | --- |
| `BackendToolCommandRun` | 运行命令。 |
| `BackendToolFilesRead` | 读取文件。 |
| `BackendToolFilesWrite` | 写入文件。 |
| `BackendToolFilesList` | 列目录。 |
| `BackendToolFilesExists` | 判断路径是否存在。 |
| `BackendToolCodeRun` | 运行代码。 |

`FlowToolCall.__call__` 可以直接返回 Python 对象，也可以构造 backend payload 并调用 `session.require_sandbox().dispatch(...)`。

## 执行流（Stream）

Backend sandbox 提供 stream API，用于组织同一个 sandbox 上的并发 backend payload。

```python
with sandbox.stream() as s1, sandbox.stream() as s2:
    f1 = s1.submit(call_a)
    f2 = s2.submit(call_b)
    result_a = f1.result()
    result_b = f2.result()
```

| Stream 行为 | 实现语义 |
| --- | --- |
| same stream | FIFO queue，单 worker thread 逐个执行。 |
| different streams | 不同 worker thread 可以并发推进。 |
| event | `record_event()` 和 `wait_event(...)` 可跨 stream 建立顺序。 |
| synchronize | `synchronize()` 等待当前 stream 已提交操作完成。 |

Session loop 当前通过 executor 逐个处理 response 中的 tool calls。backend stream 是更底层的 sandbox API，适合手动组织并发工具 payload。

## 调用路径（Call Path）

```text
run_session_loop
  -> merge_tools_for_loop(user_tools)
  -> tools_dict_to_schemas(table)
  -> executor.complete(req)
  -> for tool_call in response.message.tool_calls
       -> table[tool_name]
       -> executor.dispatch_tool(out, flow_tool, arguments)
       -> FlowToolCall.__call__(session, arguments)
       -> optional session.require_sandbox().dispatch(BackendTool*)
       -> tool_feedback_chunk(...)
```

`DefaultSessionLoopExecutor.dispatch_tool(...)` 直接调用 `tool(session, dict(arguments or {}))`。自定义 executor 可以接管工具执行策略。

## 边界条件（Boundary Conditions）

| 行为 | 当前实现 |
| --- | --- |
| built-in conflict | 用户工具名覆盖 built-in name 时抛 `ToolNameConflictError`。 |
| invalid JSON arguments | loop 写入 `invalid_tool_arguments` JSON error。 |
| unknown tool name | loop 写入 `unknown_tool` JSON error。 |
| tool exception | loop 捕获异常，写入 `tool_execution_exception` JSON error。 |
| oversized inline result | JSON 文本超过 48,000 chars 时截断。 |
| command tool guard | built-in shell tool 拒绝多行和超过 2048 字符的 command。 |

## 测试覆盖（Test Coverage）

| 行为 | 测试 |
| --- | --- |
| tool factory/result basics | `tests/unit/test_flow_tool.py`, `tests/unit/test_calls.py`, `tests/unit/test_results.py` |
| tool merge conflict | `tests/session/test_tool_registry.py` |
| custom `FlowToolCall` loop result | `tests/flow/test_flow_tool_user_subclass.py` |
| loop edge cases | `tests/session/test_run_session_loop_edges.py` |
| workflow agent tools | `tests/flow/test_workflow_agent.py` |
