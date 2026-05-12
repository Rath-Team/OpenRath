# 教程（Tutorials）

Tutorials 是 OpenRath 的统一学习入口。前半部分按步骤建立 `Session`、sandbox、tool 和 loop 的操作经验；后半部分提供可改写的脚本示例。

## 起步（First Steps）

| 顺序 | 页面 | 重点 |
| --- | --- | --- |
| 1 | [Session 基础](session_basics.md) | 创建 session、观察 chunk transcript、理解 `fork()` 与 `detach()`。 |
| 2 | [本地沙箱工具](local_sandbox_tools.md) | 打开 local backend，执行文件、命令和代码 payload。 |

## Agent 循环（Agent Loops）

| 顺序 | 页面 | 重点 |
| --- | --- | --- |
| 3 | [Session Loop 工具调用](session_loop_tools.md) | 看清 assistant tool call、backend dispatch、`tool_result` chunk 的顺序。 |
| 4 | [自定义 FlowToolCall](custom_flow_tool.md) | 继承 `FlowToolCall`，把 Python 逻辑暴露给 agent。 |

## 可运行示例（Runnable Examples）

| 页面 | 对应脚本 | 重点 |
| --- | --- | --- |
| [Session usage](examples/session_usage.md) | `example/session_usage.py` | `run_session_loop` 与 `run_session_compress` 的完整路径。 |
| [Custom tool usage](examples/custom_tool_usage.md) | `example/custom_tool_usage.py` | 把外部服务包装成 `FlowToolCall`。 |
| [Local backend workspace](examples/sandbox_backend_local.md) | `example/sandbox_backend_local.py` | `Session.to("local", spec=...)` 与本地目录绑定。 |
| [OpenSandbox backend](examples/sandbox_backend_opensandbox.md) | `example/sandbox_backend_opensandbox.py` | `Session.to("opensandbox", spec=...)` 与容器 workspace。 |
| [Trading Agents](examples/trading_agents.md) | `example/trading_agents/` | 顺序多角色研究 workflow：analyst、researcher、trader、risk/PM。 |
| [Engineering Agents](examples/engineering_agents.md) | `example/engineering_agents/` | 嵌套 workflow：lead、feature squad、backend pair、QA。 |

```{toctree}
---
maxdepth: 2
caption: 教程
---

session_basics
local_sandbox_tools
session_loop_tools
custom_flow_tool
examples/index
```
