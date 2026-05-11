# 开发者 Quickstart

这一版适合放在首页 CTA 后面，目标是让开发者 3 分钟内跑通一个 loop。

## 1. 安装

```bash
git clone https://github.com/Rath-Team/OpenRath.git
cd OpenRath
pip install -e .
cp .env.example .env
```

编辑 `.env`：

```text
OPENAI_API_KEY=...
OPENAI_BASE_URL=...
OPENAI_DEFAULT_MODEL=...
```

## 2. 写一个 agent

```python
import rath.flow as flow
from rath.session import Session

agent = flow.Agent(
    system_prompt="You are a concise assistant. Use tools when useful.",
    model="gpt-5.5",
)
```

## 3. 创建 session

```python
user = Session.from_user_message("Run `pwd` and tell me where the sandbox is.")
user = user.to("local")
```

## 4. 运行

```python
out = agent(user)
print(out)
```

## 5. 加一个工具

```python
from rath.flow.tool import FlowToolCall

class EchoTool(FlowToolCall):
    @property
    def name(self):
        return "echo_text"

    @property
    def description(self):
        return "Echo text back as JSON."

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

    def __call__(self, session, arguments):
        return {"echo": str(arguments["text"])}

agent.register_tool(EchoTool())
```

## 读者应该记住

- `Session` 是状态；
- `Agent` 是一个 thin `Workflow`；
- `FlowToolCall` 是模型可见工具；
- `Backend` 是副作用执行位置。
