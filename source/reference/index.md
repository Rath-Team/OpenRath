(python-api-reference)=
# Python API 参考

本索引用法对齐 [PyTorch 文档](https://docs.pytorch.org/docs/stable/pytorch-api.html)：按**包/模块**分页，每页一段简短职责说明；完整签名待 `sphinx-autosummary` 接入后以自动生成结果为准。阅读顺序仍建议与[用户指南](../user_guide/index.md)一致：**会话 → 后端 → 工具 → 工作流 → LLM → 杂项**。

## `rath`

* [`rath`](rath.md) — 顶层命名空间与惰性 `session` 导出。

## 会话运行时

* [`rath.session`](session.md) — `Session`、分块、`run_session_loop`、谱系与注册表等。

## 后端

* [`rath.backend`](backend.md) — 注册表、沙箱、`dispatch`、结果与流抽象。

## 工具

* [`rath.flow.tool`](flow_tool.md) — `FlowToolCall`、`ToolTable`、全局工具表与 `@tool`。

## 工作流

* [`rath.flow`](flow.md) — 包级再导出、`Workflow`、`AgentParam`、`Agent`、`Compressor` 等编排模块。

## LLM

* [`rath.llm`](llm.md) — 客户端、Provider、请求/响应数据类。

## 杂项

* [`rath.utils`](utils.md) — 环境变量等通用辅助。

```{note}
在 autosummary 铺开之前，以 `src/rath` 源码中的模块文档字符串为权威说明。
```

```{toctree}
---
caption: API 参考
maxdepth: 1
---

rath
session
backend
flow_tool
flow
llm
utils
```
