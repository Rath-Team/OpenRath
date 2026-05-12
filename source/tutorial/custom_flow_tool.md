# 自定义 FlowToolCall

这个教程创建一个 `WordCountTool`，再把它注册进 `run_session_loop`。自定义工具可以返回普通 Python 对象，loop 会把返回值序列化成 `tool_result` chunk。

## 步骤 1：定义输入 schema（Step 1）

```python
from pydantic import BaseModel


class WordCountInput(BaseModel):
    text: str
```

`FlowToolCall.parameters` 使用 JSON Schema。Pydantic model 可以直接生成这个 schema。

## 步骤 2：继承 FlowToolCall（Step 2）

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

`__call__` 接收当前 `Session` 和模型生成的 JSON arguments。工具可以只在 Python 进程内执行，也可以通过 `session.require_sandbox().dispatch(...)` 调用 backend payload。

## 步骤 3：传入 session loop（Step 3）

```python
from rath import flow
from rath.session import Session, run_session_loop

tool = WordCountTool()
agent_session = Session.from_agent_prompt("Call word_count before answering.")
user_session = Session.from_user_message(
    "Count the words in this sentence."
).to("local")

out = run_session_loop(
    user_session=user_session,
    agent_session=agent_session,
    agent_provider=flow.Provider(model="gpt-5.5"),
    tools=[tool],
    executor=scripted_executor,
)
```

`run_session_loop` 会把内置工具与传入的工具合并。工具名与内置工具名冲突时会抛出 `ToolNameConflictError`。

## 步骤 4：读取结果（Step 4）

```python
for row in out.chunk_table.rows:
    if row.kind.value == "tool_result":
        print(row.payload["name"], row.payload["content"])
```

`WordCountTool` 返回的 dict 会作为 JSON 文本写入 `tool_result` chunk。

## 关键结论

- `FlowToolCall` 同时提供 tool schema 和 Python 执行逻辑。
- `parameters` 是模型可见的 JSON Schema。
- `__call__` 是 runtime 执行入口。
- `tools=[tool]` 是把自定义工具交给 agent 的入口。
