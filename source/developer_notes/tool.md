# Tool

OpenRath 的 tool 系统把“模型可调用的能力”和“sandbox 中实际发生的副作用”分开组织。`FlowToolCall` 面向模型和 session loop，`BackendTool*` payload 面向 backend 和 sandbox。

本页说明模型 tool call 进入 OpenRath 的路径、`FlowToolCall` 的 schema/runtime 契约、backend payload 在 local/OpenSandbox 中的执行方式，以及结果写回 `Session` 的格式。

## 概览

一次工具调用会跨过三层边界：

| 层次 | 代表对象 | 负责内容 |
| --- | --- | --- |
| 模型接口 | JSON schema | 告诉模型有哪些工具、参数长什么样。 |
| Python runtime | `FlowToolCall` | 接收当前 `Session` 和模型参数，执行 Python 逻辑。 |
| Sandbox backend | `BackendTool*` payload | 在 local 或 OpenSandbox 中执行命令、文件、代码操作。 |

这个分层让自定义工具有两种写法：简单工具可以直接在 Python 进程中返回 dict；带副作用的工具可以通过 `session.require_sandbox().dispatch(...)` 把操作交给 backend。

## 源码地图

| 文件 | 负责内容 |
| --- | --- |
| `src/rath/flow/tool/base.py` | `FlowToolCall` abstract base class。 |
| `src/rath/flow/tool/system_tool.py` | built-in tools 和 backend payload factories。 |
| `src/rath/flow/tool/tool_table.py` | tool merge、schema conversion、name conflict。 |
| `src/rath/session/loop.py` | tool call dispatch、tool result serialization。 |
| `src/rath/backend/tool_types.py` | backend-facing payload dataclasses。 |
| `src/rath/backend/results.py` | backend result dataclasses。 |

## FlowToolCall 的契约

`FlowToolCall` 是 session loop 识别的工具接口。它必须提供 `name`、`parameters` 和 `__call__`。

```python
from collections.abc import Mapping
from typing import Any

from rath.flow.tool import FlowToolCall
from rath.session import Session


class AddOneTool(FlowToolCall):
    @property
    def name(self) -> str:
        return "add_one"

    @property
    def description(self) -> str | None:
        return "Add 1 to x"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
            "additionalProperties": False,
        }

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> int:
        return int(arguments["x"]) + 1
```

| 成员 | 用途 |
| --- | --- |
| `name` | LLM function tool 的名称，也是 loop 查找 Python 工具对象的 key。 |
| `description` | 可选说明，帮助模型判断什么时候调用。 |
| `parameters` | JSON Schema object，会进入 OpenAI-compatible `tools` 字段。 |
| `__call__(session, arguments)` | 执行工具。`session` 是当前输出 session，`arguments` 是模型生成的 JSON 参数。 |

`__call__` 可以返回普通 Python 对象。session loop 会把它序列化成 JSON 字符串，写入 `tool_result` chunk。

## Tool table 如何生成

`run_session_loop(...)` 每次运行都会先构造 tool table。

| 步骤 | 行为 |
| --- | --- |
| 1 | `global_system_tools()` 返回内置工具。 |
| 2 | `merge_tools_for_loop(user_tools)` 把用户工具加入表。 |
| 3 | 如果用户工具名覆盖内置工具名，抛 `ToolNameConflictError`。 |
| 4 | `tools_dict_to_schemas(table)` 生成 OpenAI-style function schema。 |

当前内置工具只有两个：

| Tool name | 行为 | Backend payload |
| --- | --- | --- |
| `run_shell_command` | 在 active sandbox workspace 中运行一条 shell command。 | `BackendToolCommandRun` |
| `write_workspace_file` | 向 sandbox workspace 写入 UTF-8 文本文件。 | `BackendToolFilesWrite` |

内置 shell tool 做了两个 guard：拒绝多行 command，拒绝超过 2048 字符的 command。这是当前实现的最小保护，具体安全边界由 backend 决定。

## 从模型响应到 tool result

模型返回 tool call 后，`run_session_loop(...)` 会执行以下路径：

```text
assistant tool_calls
  -> table[tool_name]
  -> executor.dispatch_tool(out, flow_tool, arguments)
  -> flow_tool(out, arguments)
  -> Python result or backend dispatch result
  -> tool_feedback_chunk(...)
  -> out.chunk_table
```

关键点是 `out`。loop 会先创建输出 session，并把输入 user session 的 sandbox 迁移到 `out`。因此工具执行时拿到的是输出 session，工具写入的副作用和 tool result 都属于这一轮输出。

```python
def __call__(self, session: Session, arguments):
    sandbox = session.require_sandbox()
    return sandbox.dispatch(...)
```

工具执行结果会被 `_summarize_dispatch_result(...)` 转成字符串。常见映射如下：

| 返回值 | 写入 `tool_result` 的内容 |
| --- | --- |
| 普通 dict/list/int/str | JSON 文本；超过 48,000 chars 会截断。 |
| Pydantic model | `model_dump(mode="json")` 后转 JSON。 |
| `CommandResult` | `exit_code`、`stdout`、`stderr`、`elapsed_ms`。 |
| `FileContent` | `data`，超过 12,000 chars 会截断。 |
| `FileEntries` | 最多前 500 个 entries。 |
| `FileWriteResult` | `bytes_written`。 |
| `CodeResult` | `text`、`stdout`、`stderr`、`error`。 |
| `ToolExecutionFailure` | `ok=false`、`error_kind`、`message`、`detail`。 |
| `bool` | `{"ok": true}` 或 `{"ok": false}`。 |

## BackendTool payload

Backend payload 是更底层的 sandbox 操作描述。它们不直接暴露给模型；通常由 `FlowToolCall` 构造并交给 sandbox。

| Payload | 字段 | 用途 |
| --- | --- | --- |
| `BackendToolCommandRun` | `cmd`、`env`、`cwd`、`stdin`、`timeout` | 运行 shell command。 |
| `BackendToolFilesRead` | `path`、`encoding` | 读取文件。 |
| `BackendToolFilesWrite` | `path`、`data`、`mode` | 写文件。 |
| `BackendToolFilesList` | `path` | 列目录。 |
| `BackendToolFilesExists` | `path` | 判断路径是否存在，返回 bool。 |
| `BackendToolCodeRun` | `code`、`language`、`timeout` | 运行代码片段。 |

示例：自定义工具可以把模型参数转成 backend payload。

```python
from rath.backend import BackendToolFilesRead
from rath.flow.tool import FlowToolCall


class ReadTextTool(FlowToolCall):
    @property
    def name(self):
        return "read_text"

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        }

    def __call__(self, session, arguments):
        call = BackendToolFilesRead(path=str(arguments["path"]))
        return session.require_sandbox().dispatch(call)
```

## 什么时候直接返回 Python 对象

直接返回 Python 对象适合无外部副作用的工具，例如字符串处理、参数校验、轻量计算、读取进程内缓存。

```python
def __call__(self, session, arguments):
    text = str(arguments["text"])
    return {"words": len(text.split())}
```

这种工具不需要 sandbox，也不会触发 backend lifecycle。

## 什么时候使用 backend dispatch

使用 backend dispatch 适合需要副作用或隔离环境的工具，例如读写 workspace、运行 shell command、执行代码、访问容器中的依赖。

```python
def __call__(self, session, arguments):
    sandbox = session.require_sandbox()
    return sandbox.dispatch(...)
```

这种工具要求进入 loop 的 user session 已经绑定 sandbox target 或 open handle。否则 `require_sandbox()` 会抛 `RuntimeError`。

## Stream API 的位置

`BackendSandbox.stream()` 是 backend 层的并发 API。它和模型 tool call loop 属于不同层。

| 场景 | 当前行为 |
| --- | --- |
| session loop 处理模型返回的 tool calls | 逐个调用 executor dispatch。 |
| 手动提交 backend payload | 可以创建多个 stream。 |
| 同一个 stream | FIFO queue，单 worker thread 逐个执行。 |
| 不同 stream | 不同 worker thread 可并发推进。 |
| stream event | `record_event()` 和 `wait_event(...)` 可建立跨 stream 顺序。 |

编写普通 `FlowToolCall` 通常不需要直接接触 stream。手动并发组织 backend payload 时再使用它。

## 边界条件

| 行为 | 当前实现 |
| --- | --- |
| 用户工具名覆盖内置工具 | `merge_tools_for_loop(...)` 抛 `ToolNameConflictError`。 |
| 模型返回不可解析 JSON arguments | loop 写入 `invalid_tool_arguments` JSON error。 |
| 模型请求未知工具 | loop 写入 `unknown_tool` JSON error。 |
| 工具执行抛异常 | loop 捕获异常，写入 `tool_execution_exception` JSON error。 |
| 普通返回值过长 | JSON 文本超过 48,000 chars 时截断。 |
| `FileContent` 过长 | 文本超过 12,000 chars 时截断。 |
| `FileEntries` 过多 | 最多序列化前 500 项。 |
| shell command 多行或过长 | built-in shell tool 抛 `ValueError`，loop 会转成 tool execution error。 |

## 读代码时的检查点

| 想确认的问题 | 看哪里 |
| --- | --- |
| `FlowToolCall` 最小接口 | `src/rath/flow/tool/base.py` |
| 内置工具实现 | `src/rath/flow/tool/system_tool.py` |
| 名称冲突与 schema 排序 | `src/rath/flow/tool/tool_table.py` |
| tool result 如何写回 session | `src/rath/session/loop.py` |
| backend payload 类型 | `src/rath/backend/tool_types.py` |
| backend result 类型 | `src/rath/backend/results.py` |

## 测试覆盖

| 行为 | 测试 |
| --- | --- |
| tool factory/result basics | `tests/unit/test_flow_tool.py`, `tests/unit/test_calls.py`, `tests/unit/test_results.py` |
| tool merge conflict | `tests/session/test_tool_registry.py` |
| custom `FlowToolCall` loop result | `tests/flow/test_flow_tool_user_subclass.py` |
| loop edge cases | `tests/session/test_run_session_loop_edges.py` |
| workflow agent tools | `tests/flow/test_workflow_agent.py` |
