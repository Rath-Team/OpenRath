# 可运行示例

这些页面对应仓库里的 `example/` 脚本和子目录。核心教程之后，可以通过这些示例查看 session、tool、sandbox 和 workflow 在真实脚本中的组合方式。

## 示例地图
| 顺序 | 页面 | 对应脚本 | 内容 |
| --- | --- | --- | --- |
| 1 | [Session 用法示例](session_usage.md) | `example/session_usage.py` | 从 session 创建到 loop 和 compress 的连续路径。 |
| 2 | [自定义工具示例](custom_tool_usage.md) | `example/custom_tool_usage.py` | 把外部服务包装成 `FlowToolCall`。 |
| 3 | [本地后端示例](sandbox_backend_local.md) | `example/sandbox_backend_local.py` | local backend 的临时目录和项目目录绑定。 |
| 4 | [OpenSandbox 后端示例](sandbox_backend_opensandbox.md) | `example/sandbox_backend_opensandbox.py` | OpenSandbox backend、workspace bind、服务健康检查。 |
| 5 | [Trading Agents](trading_agents.md) | `example/trading_agents/` | 多角色 workflow、外部数据工具和 session 级并行分支。 |
| 6 | [Engineering Agents](engineering_agents.md) | `example/engineering_agents/` | 嵌套 workflow、工程任务拆分和可并行子任务。 |

## 运行前准备
所有涉及真实 LLM 的示例都需要配置 OpenAI-compatible 网关。文档不会写入任何真实 key；API key 应通过 shell 环境变量或本地 `.env` 管理：

```bash
export OPENAI_API_KEY=...
export OPENAI_BASE_URL=...
export OPENAI_DEFAULT_MODEL=...
```

涉及外部服务的示例会在页面中说明额外变量。例如 Trading Agents 需要显式设置 `ALPHA_VANTAGE_API_KEY`，OpenSandbox 示例需要 OpenSandbox 服务端可用。

## 读示例时看什么
| 观察对象 | 为什么重要 |
| --- | --- |
| stdout | 可以看到最后一个 assistant message 或输出 session。 |
| workspace | 可以确认工具是否真的写入文件。 |
| chunk table | 可以确认 user、assistant、tool result 的顺序。 |
| workflow repr | 可以确认哪些 `AgentParam` 被直接登记。 |
| 环境变量 | 可以确认模型网关、外部 API、OpenSandbox 服务是否生效。 |

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
