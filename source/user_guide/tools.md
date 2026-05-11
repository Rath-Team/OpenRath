# 工具

当前 OpenRath 的工具体系只有一条主线：`FlowToolCall`。没有全局用户 `ToolTable`、没有 `@tool` 装饰器，也没有 `ToolRegistration`。

## FlowToolCall 接口

自定义工具需要继承 `FlowToolCall`：

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
        return "Add 1 to x."

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

`parameters` 会转成 OpenAI function-style tool schema。框架不会自动做 Pydantic 校验；如果需要强校验，在 `__call__` 里自行调用 Pydantic model。

## 内置系统工具

`global_system_tools()` 返回两个内置工具实例：

| 工具名 | 行为 |
| --- | --- |
| `run_shell_command` | 读取 `{"cmd": "..."}`，构造 `BackendToolCommandRun`，在 session sandbox 内执行。 |
| `write_workspace_file` | 读取 `{"path": "...", "content": "..."}`，构造 `BackendToolFilesWrite`，写入 sandbox workspace。 |

`run_shell_command` 会拒绝多行命令，并限制命令长度不超过 2048 字符。

## 合并工具

`run_session_loop(..., tools=[...])` 内部会调用：

```python
from rath.flow.tool import merge_tools_for_loop

table = merge_tools_for_loop(user_tools)
```

合并规则：

1. 先复制内置系统工具；
2. 再加入用户传入的 `FlowToolCall` 实例；
3. 如果用户工具名与内置工具同名，抛 `ToolNameConflictError`。

`tools_dict_to_schemas(table)` 会按工具名排序，输出 `RathLLMFunctionTool` 元组。

## 工具执行路径

在 `run_session_loop` 中，模型返回 tool call 后：

1. 若 arguments 无法解析为 JSON，追加 `tool_result`，内容为 `{"ok": false, "error_kind": "invalid_tool_arguments", ...}`。
2. 若工具名不存在，追加 `tool_result`，内容为 `{"ok": false, "error_kind": "unknown_tool", ...}`。
3. 若工具存在，调用 `executor.dispatch_tool(out_session, flow_tool, parsed_arguments)`。
4. 默认执行器会直接执行 `flow_tool(session, arguments)`。
5. 返回值会被序列化成 JSON，写入 `tool_result` chunk。

后端工具返回值会被特殊处理，例如 `CommandResult` 会转为包含 `exit_code`、`stdout`、`stderr`、`elapsed_ms` 的 JSON。

## FlowToolCall 与 BackendTool 的区别

| 层级 | 类型 | 谁消费 | 用途 |
| --- | --- | --- | --- |
| 模型/循环层 | `FlowToolCall` | `run_session_loop` / `SessionLoopExecutor` | 给 LLM 暴露 schema，并处理调用参数。 |
| 沙箱执行层 | `BackendTool*` | `Backend.dispatch` | 描述具体后端动作，例如命令、文件读写、代码执行。 |

内置 `RunShellCommandTool` 是 `FlowToolCall`，它在 `__call__` 内部构造 `BackendToolCommandRun`。而 `flow_tool_command_run(...)` 直接返回后端工具载荷，不会自动进入 LLM schema。

## 放入 Agent

```python
import rath.flow as flow

agent = flow.Agent(
    system_prompt="Use add_one when arithmetic is requested.",
    model="gpt-5.5",
    tools=[AddOneTool()],
)
```

也可以直接传给 `run_session_loop`：

```python
out = run_session_loop(
    user_session=user_session,
    agent_session=agent_session,
    agent_provider=provider,
    tools=[AddOneTool()],
)
```

**下一篇：** [工作流](workflow_agent.md)
