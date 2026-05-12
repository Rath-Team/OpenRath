# 示例

`example/` 目录提供可运行脚本。请在仓库根目录完成开发安装（`pip install -e .` 或 `uv sync`），并按[用户指南](../user_guide/index.md)顺序理解组件；每个示例在下方有**独立说明页**。

```{note}
会调用模型的示例需在环境中导出 **LLM** 相关变量（如 `OPENAI_API_KEY`），并在代码中构造 `Provider`（根目录示例可复用 `example/_openai_provider.py`）；OpenSandbox 另需服务与 `OPEN_SANDBOX_DOMAIN` 等配置。详见各页「依赖」一节。
```

**源码目录：** [github.com/Rath-Team/OpenRath/tree/main/example](https://github.com/Rath-Team/OpenRath/tree/main/example)。

```{toctree}
---
caption: 示例
maxdepth: 1
---

session_usage
custom_tool_usage
sandbox_backend_local
sandbox_backend_opensandbox
```

