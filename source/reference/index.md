# API Reference
本节按真实包结构整理 public API。每个页面包含三类信息：

| 信息 | 用途 |
| --- | --- |
| 源码 | 对应源码文件，方便直接跳回实现。 |
| 公共契约 | 常用签名、参数、返回值和异常。 |
| 自动文档 | 从当前源码导入的 class/function 文档。 |

## 包结构
| 包 | 内容 |
| --- | --- |
| [`rath`](rath.md) | 包级入口。 |
| [`rath.session`](session.md) | `Session`、chunk、loop、compress、lineage、registry。 |
| [`rath.backend`](backend.md) | 后端抽象、沙箱、工具载荷、结果、注册表、stream。 |
| [`rath.flow`](flow.md) | `Workflow`、`AgentParam`、`Agent`、`SessionCompressor`。 |
| [`rath.flow.tool`](flow_tool.md) | `FlowToolCall`、内置系统工具、后端工具工厂、schema 合并。 |
| [`rath.llm`](llm.md) | `Provider`、请求/响应类型、OpenAI-compatible client。 |
| [`rath.utils`](utils.md) | `.env` 和项目根路径辅助。 |

```{toctree}
---
maxdepth: 2
caption: API Reference
---

rath
session
backend
flow
flow_tool
llm
utils
```
