# PyTorch 类比讲法

OpenRath 可以用 PyTorch 类比快速解释，但要明确边界：它借的是 API 组织方式，不是张量计算能力。

## 类比表

| PyTorch | OpenRath | 讲法 |
| --- | --- | --- |
| `Tensor` | `Session` | 状态对象，贯穿计算/工作流。 |
| `nn.Module` | `Workflow` | 有 `forward`，可组合。 |
| child modules | `AgentParam` attributes | 属性赋值时被登记，可枚举。 |
| device | `Backend` | 决定副作用在哪里执行。 |
| functional ops | `flow_tool_*` | 构造后端工具载荷。 |

## 推荐话术

OpenRath tries to make agent workflows feel like writing small PyTorch modules: state is explicit, modules compose, and runtime placement is not hidden inside prompt strings.

中文版本：

OpenRath 希望把 Agent 工作流写成类似 PyTorch 模块的形式：状态显式存在，模块可以组合，执行环境不是藏在 prompt 里的隐式副作用。

## 不应该这样讲

不要说 OpenRath 是 “PyTorch for Agents” 后就结束。这个说法容易让人误解为：

- 有 autograd；
- 有 tensor；
- 有训练循环；
- 有 GPU 计算抽象；
- 有 optimizer。

更准确的说法是：OpenRath uses PyTorch-like API ergonomics for session-based agent workflows.

## 最好配的 demo

```python
class MyWorkflow(Workflow):
    def __init__(self):
        super().__init__()
        self.agent = AgentParam(
            Session.from_agent_prompt("You are concise."),
            Provider(model="gpt-5.5"),
        )

    def forward(self, session):
        return run_session_loop(
            session,
            self.agent.agent_session,
            agent_provider=self.agent.provider,
        )
```

这段代码能让工程师立即理解 `Workflow` / `AgentParam` 的组织方式。
