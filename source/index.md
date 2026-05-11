(openrath-documentation)=
# OpenRath 文档

OpenRath 是面向动态多智能体工作流的 Python 框架，采用类似 Torch 的 API 设计，让大规模 Agent 的模块化开发成为可能。

* [安装](install.md)
* [用户指南](user_guide/index.md)
  * [设计概览](user_guide/concepts.md)
  * [主要组件](user_guide/main_components.md)
  * [会话](user_guide/session.md)
  * [沙箱后端](user_guide/backends.md)
  * [工具](user_guide/tools.md)
  * [工作流](user_guide/workflow_agent.md)
  * [LLM 请求接口](user_guide/llm.md)
* [API 参考](reference/index.md)
  * [`rath`](reference/rath.md)
  * [`rath.session`](reference/session.md)
  * [`rath.backend`](reference/backend.md)
  * [`rath.flow`](reference/flow.md)
  * [`rath.flow.tool`](reference/flow_tool.md)
  * [`rath.llm`](reference/llm.md)
  * [`rath.utils`](reference/utils.md)
* [示例](examples/index.md)
  * [如何使用 Session](examples/session_usage.md)
  * [如何自定义工具](examples/custom_tool_usage.md)
  * [如何绑定本地沙箱](examples/sandbox_backend_local.md)
  * [如何绑定 OpenSandbox](examples/sandbox_backend_opensandbox.md)

```{toctree}
---
maxdepth: 3
caption: 站点导航
hidden:
---

install
user_guide/index
reference/index
examples/index
```
