# Tutorials
Tutorials 是 OpenRath 的学习入口。这里按使用顺序组织内容：先构造 `Session`，再理解工具执行位置，随后进入 agent loop 和 multi-agent workflow。

教程以代码片段、关键行解释和运行观察为主，覆盖从 API 使用到 workflow 改写的常见路径。

## 学习路径
| 顺序 | 页面 | 内容 |
| --- | --- | --- |
| 1 | [Session 基础](session_basics.md) | 创建 user session 和 agent session，理解 `fork()`、`detach()`、backend placement。 |
| 2 | [本地沙箱工具](local_sandbox_tools.md) | 直接打开 local backend，理解文件、命令和代码 payload 如何围绕 workspace 执行。 |
| 3 | [Session Loop 工具调用](session_loop_tools.md) | 看清模型 tool call、tool dispatch、`tool_result` chunk 和下一轮 completion 的关系。 |
| 4 | [自定义 FlowToolCall](custom_flow_tool.md) | 定义自己的工具 schema 和 Python 执行逻辑，并交给 session loop。 |
| 5 | [可运行示例](examples/index.md) | 从仓库脚本学习真实 workflow、OpenSandbox 和 multi-agent 组合。 |

## 按任务选择教程
| 任务 | 先读 |
| --- | --- |
| 只想理解 OpenRath 的状态模型 | [Session 基础](session_basics.md) |
| 想确认工具会在哪个目录里执行 | [本地沙箱工具](local_sandbox_tools.md) |
| 想知道 agent 如何连续调用工具 | [Session Loop 工具调用](session_loop_tools.md) |
| 想把外部 API 包装成模型可调用工具 | [自定义 FlowToolCall](custom_flow_tool.md) |
| 想写一个多角色 agent 流程 | [Trading Agents](examples/trading_agents.md) 和 [Engineering Agents](examples/engineering_agents.md) |
| 想接 OpenSandbox | [OpenSandbox backend](examples/sandbox_backend_opensandbox.md) |

## 阅读方式
每页使用相同结构：

1. 先读覆盖内容，确认这一页解决的问题。
2. 跟着代码步骤理解 API 边界。
3. 对照关键行解释，确认状态在哪一行改变。
4. 运行或改写练习，把示例转成自己的代码。
5. 行为不符合预期时，先看常见问题，再回到 Developer Notes 查源码层解释。

## 可运行示例
这些页面对应仓库里的 `example/` 脚本和子目录：

| 页面 | 对应脚本 | 重点 |
| --- | --- | --- |
| [Session 用法示例](examples/session_usage.md) | `example/session_usage.py` | `Session`、`run_session_loop`、`run_session_compress` 的连续路径。 |
| [自定义工具示例](examples/custom_tool_usage.md) | `example/custom_tool_usage.py` | 把外部服务包装成 `FlowToolCall`。 |
| [本地后端示例](examples/sandbox_backend_local.md) | `example/sandbox_backend_local.py` | `Session.to("local", spec=...)` 与本地目录绑定。 |
| [OpenSandbox 后端示例](examples/sandbox_backend_opensandbox.md) | `example/sandbox_backend_opensandbox.py` | `Session.to("opensandbox", spec=...)` 与容器 workspace。 |
| [Trading Agents](examples/trading_agents.md) | `example/trading_agents/` | 顺序多角色研究 workflow。 |
| [Engineering Agents](examples/engineering_agents.md) | `example/engineering_agents/` | 嵌套 workflow。 |

```{toctree}
---
maxdepth: 2
caption: Tutorials
---

session_basics
local_sandbox_tools
session_loop_tools
custom_flow_tool
examples/index
```
