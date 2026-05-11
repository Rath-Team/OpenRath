(user-guide-root)=
# 用户指南

本指南的组织方式接近 [PyTorch 文档](https://docs.pytorch.org/docs/stable/index.html)中的 **用户指南** 路径：先有简短的「入门」页面，再按顺序阅读**组件**章节。每一章对应智能体循环中的一层——**会话状态、沙箱后端、工具、工作流编排、LLM I/O**。

若需要完整心智模型，请先读[设计概览](concepts.md)与 [OpenRath 主要组件](main_components.md)，再自上而下浏览下方 `toctree`。

```{toctree}
---
caption: 入门
maxdepth: 1
---

concepts
main_components
```

```{toctree}
---
caption: 组件
maxdepth: 1
---

session
backends
tools
workflow_agent
llm
```
