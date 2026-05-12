# 可运行示例（Runnable Examples）

这些页面对应仓库里的 `example/` 脚本和子目录。它们展示真实 API 的使用路径：前几个例子适合学习单个能力，multi-agent 例子适合理解 `Workflow` 如何把多个 agent 串成可检查的 session pipeline。

| 页面 | 对应脚本 | 重点 |
| --- | --- | --- |
| [Session usage](session_usage.md) | `example/session_usage.py` | `Session`、`run_session_loop`、`run_session_compress`。 |
| [Custom tool usage](custom_tool_usage.md) | `example/custom_tool_usage.py` | 继承 `FlowToolCall`，把工具交给 `flow.Agent`。 |
| [Local backend workspace](sandbox_backend_local.md) | `example/sandbox_backend_local.py` | `Session.to("local", spec=...)`。 |
| [OpenSandbox backend](sandbox_backend_opensandbox.md) | `example/sandbox_backend_opensandbox.py` | `Session.to("opensandbox", spec=...)`。 |
| [Trading Agents](trading_agents.md) | `example/trading_agents/` | 多角色交易研究 workflow，包含一个实时市场数据工具。 |
| [Engineering Agents](engineering_agents.md) | `example/engineering_agents/` | 嵌套工程团队 workflow，展示 workflow 内再组合 workflow。 |

运行这些脚本前，先完成 [Install](../../install.md) 中的环境配置。涉及 OpenSandbox、外部行情 API 或真实 LLM 的页面会在正文开头说明额外配置。

```{toctree}
---
maxdepth: 2
caption: 可运行示例
---

session_usage
custom_tool_usage
sandbox_backend_local
sandbox_backend_opensandbox
trading_agents
engineering_agents
```
