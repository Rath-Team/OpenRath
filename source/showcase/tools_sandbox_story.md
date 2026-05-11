# 工具与沙箱安全讲解

Agent 工具调用最容易失控的地方，是模型输出的函数名和参数会直接触发副作用。OpenRath 把这条链拆成两个层级：`FlowToolCall` 和 `BackendTool`。

## 讲法

模型永远不直接拿到 Python 函数。它只能看到 schema。真正执行时，OpenRath 用工具名找到一个 `FlowToolCall` 实例，再由这个实例决定如何处理参数。

内置 shell 工具的路径是：

```text
run_shell_command
→ RunShellCommandTool.__call__
→ BackendToolCommandRun
→ session.require_sandbox().dispatch(...)
→ LocalBackend 或 OpenSandboxBackend
→ CommandResult
→ tool_result chunk
```

## 为什么这对展示有用

这个设计能清楚说明 OpenRath 不是“把所有工具函数挂到全局变量上”。工具是实例，schema 是实例的一部分，执行位置由 session 的 sandbox 决定。

## 展示 demo

```python
from rath.flow.tool import FlowToolCall

class AddOneTool(FlowToolCall):
    @property
    def name(self):
        return "add_one"

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
        }

    def __call__(self, session, arguments):
        return int(arguments["x"]) + 1
```

这个 demo 的好处是它没有外部服务依赖，适合测试；再展示 `RunShellCommandTool`，就能说明 Python 内部工具和 sandbox 工具都能走同一层抽象。

## 风险也要讲

当前内置 `run_shell_command` 只做了基础限制：拒绝多行命令、限制长度。它不是完整安全策略。真正对外部署时，应该使用容器/远程 sandbox，并在业务层限制工具、路径和命令能力。
