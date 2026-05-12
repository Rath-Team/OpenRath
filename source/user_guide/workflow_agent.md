# 工作流与 Agent

`Workflow` 是一个可调用对象：输入 `Session`，输出 `Session`。它本身不发请求；真实 LLM 请求通常由 `run_session_loop` 完成。

## Workflow

继承 `Workflow` 并实现 `forward(self, session) -> Session`：

```python
from rath.flow import Workflow, AgentParam, Provider
from rath.session import Session, run_session_loop


class SingleAgentWorkflow(Workflow):
    def __init__(self) -> None:
        super().__init__()
        self.agent = AgentParam(
            agent_session=Session.from_agent_prompt("You are concise."),
            provider=Provider(model="gpt-5.5"),
        )

    def forward(self, session: Session) -> Session:
        return run_session_loop(
            user_session=session,
            agent_session=self.agent.agent_session,
            agent_provider=self.agent.provider,
        )
```

把 `AgentParam` 赋值到属性时，`Workflow.__setattr__` 会把它登记到内部 `_agents`。`named_agents()` 会按名称排序返回这些 agent 参数。

## AgentParam

`AgentParam` 只有两个字段：

| 字段 | 作用 |
| --- | --- |
| `agent_session` | agent 侧 prompt/context，进入 LLM messages 时排在 user session 历史之前。 |
| `provider` | 模型名、采样参数、tool choice 等 OpenAI-style 配置。 |

它刻意不持有 HTTP client、executor、sandbox 或 memory store。这样同一个 agent 参数可以被不同执行器复用。

## Agent

`rath.flow.Agent` 是 `Workflow` 的薄封装：

```python
import rath.flow as flow

agent = flow.Agent(
    system_prompt="You are a helpful assistant.",
    model="gpt-5.5",
)

out_session = agent(user_session)
```

构造时会创建：

- `self.agent = AgentParam(Session.from_agent_prompt(system_prompt), Provider(model=model))`
- `self.tools = list(tools or [])`

调用时进入 `run_session_loop(...)`。可以通过：

```python
agent.register_tool(tool)
agent.unregister_tool("tool_name")
```

维护工具列表。`register_tool` 对同名工具是幂等的；如果列表里已有同名工具，它不会重复加入。

## `Compressor`（会话压缩）

`Compressor` 是 `Workflow` 子类，把输入 session 交给 `run_session_compress`，得到仅含 user 分块的压缩后 session。

```python
from rath.flow import Compressor
from rath.llm import Provider

compressor = Compressor(
    compress_instruction="Summarize the transcript faithfully.",
    provider=Provider(api_key="sk-...", model="gpt-4o"),
)
compressed = compressor.forward(out_session)
```

## run_session_loop 生命周期

`run_session_loop` 的关键行为：

1. 合并内置工具与 `tools=[...]` 用户工具；
2. 从 `user_session` 取走 sandbox，并绑定到输出 session；
3. 注册 user、agent、output 三个 session；
4. 把 `agent_session` messages 拼在用户历史之前；
5. 调用 `executor.complete(req)`；
6. 若 assistant 返回 tool calls，执行工具并追加 `tool_result`；
7. 若无 tool calls，追加 assistant chunk 并返回；
8. 最多执行 `max_tool_rounds` 轮工具调用。

默认执行器是（`provider` 与传入 `run_session_loop` 的 `agent_provider` 相同）：

```python
DefaultSessionLoopExecutor(RathOpenAIChatClient(provider))
```

如果需要缓存、替换模型网关、mock 测试或批处理，可以实现同名协议方法：`complete(...)`、`dispatch_tool(...)`、`tool_schemas()`。

## 自定义执行器的最小接口

```python
class MyExecutor:
    def complete(self, req):
        ...

    def dispatch_tool(self, session, tool, arguments):
        return tool(session, arguments)

    def tool_schemas(self):
        return ()
```

`tool_schemas()` 返回空元组时，loop 会用本轮合并后的 `FlowToolCall` 列表自动生成 schema。

**下一篇：** [LLM 请求接口](llm.md)
