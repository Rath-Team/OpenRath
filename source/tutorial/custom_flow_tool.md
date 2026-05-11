# 自定义 FlowToolCall

本教程创建一个 `WordCountTool`，并把它注册进 `run_session_loop(...)`。内容覆盖自定义工具的主要路径：schema 如何暴露给模型，Python callable 如何执行，结果如何写回 session。

## 覆盖内容
| 主题 | 结果 |
| --- | --- |
| tool schema | `name`、`description`、`parameters` 如何暴露给模型。 |
| argument validation | 用 Pydantic 校验模型生成的 JSON arguments。 |
| runtime execution | `__call__(session, arguments)` 是工具执行入口。 |
| result serialization | 普通 Python 返回值会被 loop 序列化成 `tool_result`。 |
| sandbox access | 工具可以通过 `session.require_sandbox()` 调用 backend。 |

## 步骤 1：定义输入 schema
```python
from pydantic import BaseModel, Field


class WordCountInput(BaseModel):
    text: str = Field(description="Text to count.")
```

关键行：

| 行 | 解释 |
| --- | --- |
| `BaseModel` | 用结构化类型描述工具输入。 |
| `Field(description=...)` | 帮助模型理解参数含义。 |
| `model_json_schema()` | 后续会转成 LLM tool schema 的 `parameters`。 |

## 步骤 2：继承 FlowToolCall
```python
from collections.abc import Mapping
from typing import Any

from rath.flow.tool import FlowToolCall
from rath.session import Session


class WordCountTool(FlowToolCall):
    @property
    def name(self) -> str:
        return "word_count"

    @property
    def description(self) -> str:
        return "Count words in a text string."

    @property
    def parameters(self) -> Mapping[str, Any]:
        return WordCountInput.model_json_schema()

    def __call__(
        self,
        session: Session,
        arguments: Mapping[str, Any],
    ) -> dict[str, int]:
        model = WordCountInput.model_validate(dict(arguments or {}))
        return {"words": len(model.text.split())}
```

关键行：

| 行 | 解释 |
| --- | --- |
| `name` | 模型返回 tool call 时会使用这个名字。 |
| `description` | 让模型知道什么时候调用工具。 |
| `parameters` | JSON Schema，决定模型生成什么 arguments。 |
| `model_validate(...)` | 把模型生成的 dict 校验成 Python 对象。 |
| `return {"words": ...}` | loop 会把 dict 序列化为 JSON 文本写入 `tool_result`。 |

`__call__` 接收当前 `Session`。这意味着工具可以读取 session 状态，也可以通过 `session.require_sandbox().dispatch(...)` 调用文件、命令或代码 payload。

## 步骤 3：传入 session loop
```python
from rath import flow
from rath.session import Session, run_session_loop

tool = WordCountTool()
agent_session = Session.from_agent_prompt(
    "Call word_count before answering word-count questions."
)
user_session = Session.from_user_message(
    "Count the words in: OpenRath keeps agent state explicit."
).to("local")

out = run_session_loop(
    user_session=user_session,
    agent_session=agent_session,
    agent_provider=flow.Provider(model="gpt-5.5"),
    tools=[tool],
    executor=scripted_executor,
)
```

关键行：

| 行 | 解释 |
| --- | --- |
| `tools=[tool]` | 把自定义工具交给 loop。 |
| `.to("local")` | 在教程中明确 user session 的执行位置。 |
| `executor=scripted_executor` | 教程或测试中可以固定模型响应。真实运行时可以省略。 |

`run_session_loop(...)` 会把内置工具和传入工具合并。工具名与内置工具名冲突时会抛出 `ToolNameConflictError`。

## 步骤 4：读取结果
```python
for row in out.chunk_table.rows:
    if row.kind.value == "tool_result":
        print(row.payload["name"], row.payload["content"])
```

观察结果：

- `row.payload["name"]` 为 `word_count`。
- `row.payload["content"]` 为 JSON 文本，例如 `{"words": 5}`。
- 如果工具抛异常，loop 会把错误包装成模型可见的工具失败 payload。

## 步骤 5：让工具访问 sandbox
如果工具需要读写 workspace，可以在 `__call__` 中取得 sandbox：

```python
from rath.backend import BackendToolFilesRead

def __call__(self, session: Session, arguments: Mapping[str, Any]) -> dict[str, int]:
    model = WordCountInput.model_validate(dict(arguments or {}))
    sandbox = session.require_sandbox()
    content = sandbox.dispatch(
        BackendToolFilesRead(path=model.text, encoding="utf-8")
    )
    text = str(content.data)
    return {"words": len(text.split())}
```

这类工具需要 user session 已经绑定 backend。否则 `session.require_sandbox()` 会失败。

## 常见问题
| 现象 | 检查方向 |
| --- | --- |
| 模型不调用工具 | 增强 tool description 或 system prompt。 |
| 参数校验失败 | 查看 Pydantic error，确认 `parameters` 和 prompt 对齐。 |
| 工具名冲突 | 换一个唯一 `name`，避开内置工具名。 |
| 工具需要文件但找不到 sandbox | 确认 user session 已 `.to("local")` 或 `.to("opensandbox")`。 |
| 返回值不可 JSON 序列化 | 返回 dict、list、str、int 或 Pydantic model。 |

## 练习
1. 给 `WordCountInput` 增加 `lowercase: bool` 参数。
2. 让工具同时返回 `characters` 和 `lines`。
3. 把工具改成读取 workspace 文件，并统计文件内容的词数。

## 小结

- `FlowToolCall` 同时提供 tool schema 和 Python 执行逻辑。
- `parameters` 是模型可见的 JSON Schema。
- `__call__` 是 runtime 执行入口。
- `tools=[tool]` 是把自定义工具交给 agent 的入口。
