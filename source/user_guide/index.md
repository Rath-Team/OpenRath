# 用户指南

本指南按运行路径组织，而不是按源码目录堆 API：先理解 `Session` 如何承载状态，再看沙箱如何执行工具，最后看 `Workflow` 如何组织 agent。

## 推荐顺序

1. [设计概览](concepts.md)：OpenRath 的心智模型和 PyTorch 类比边界。
2. [主要组件](main_components.md)：每个模块负责什么，不负责什么。
3. [会话](session.md)：`Session`、chunk、sandbox 绑定、lineage、压缩。
4. [沙箱后端](backends.md)：`Backend`、`BackendSandbox`、工具载荷和结果。
5. [工具](tools.md)：`FlowToolCall`、内置工具、自定义工具和 schema。
6. [工作流](workflow_agent.md)：`Workflow`、`AgentParam`、`Agent` 和 `run_session_loop`。
7. [LLM 请求接口](llm.md)：`Provider`、请求/响应类型、默认 OpenAI-compatible 客户端。

```{toctree}
---
maxdepth: 2
caption: 用户指南
---

concepts
main_components
session
backends
tools
workflow_agent
llm
```
