# 一页纸介绍

OpenRath 是一个面向 Agent 工作流的 Python 框架。它把对话历史、工具调用、沙箱执行和 LLM 请求拆成可以组合的运行时对象，让多智能体系统不再只是一段越来越长的 prompt。

## 一句话

OpenRath lets you build tool-using agents as composable, session-centered workflows.

## 为什么需要它

普通 agent demo 往往把状态塞在 prompt 里，把工具直接写成临时函数，把执行环境和模型请求混在一起。这样能跑，但很难扩展到多 agent、多工具、多轮实验或可追踪的工作流。

OpenRath 的做法是拆开四件事：

| 问题 | OpenRath 对象 |
| --- | --- |
| 状态放在哪里？ | `Session` |
| 工具在哪里运行？ | `BackendSandbox` |
| 模型看见什么工具？ | `FlowToolCall` |
| 多个 agent 怎么组织？ | `Workflow` / `AgentParam` |

## 最小代码

```python
import rath.flow as flow
from rath.session import Session

agent = flow.Agent(
    system_prompt="You are a helpful assistant.",
    model="gpt-5.5",
)

user = Session.from_user_message("List files and summarize them.")
user = user.to("local")

out = agent(user)
print(out)
```

## 当前能力

- 本地沙箱与 OpenSandbox 适配；
- OpenAI-compatible 同步聊天客户端；
- 内置 shell / file-write 工具；
- 自定义 `FlowToolCall`；
- `Workflow` / `AgentParam` 组合；
- session lineage、fork、detach、compress。

## 最适合展示的 demo

1. 让 agent 在本地 sandbox 中执行 `run_shell_command`。
2. 让 agent 写入一个文件，再读取输出 session 的 `tool_result` chunk。
3. 自定义一个 `FlowToolCall`，证明工具系统不是写死的。
4. 用 `Workflow` 包一层，展示未来可以组合多个 agent。
