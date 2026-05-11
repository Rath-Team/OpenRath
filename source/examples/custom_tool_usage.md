(example-custom-tool)=
# 如何自定义工具

演示如何实现继承 **`FlowToolCall`** 的自定义工具（本例为调用智谱 **GLM-Image** HTTP API 的 `image_gen`），用 **`flow.Agent`** 注册 `tools=[...]`，并在**本地沙箱**工作目录下跑通一轮对话。

## 运行

```bash
python example/custom_tool_usage.py
```

需配置 **`ZHIPU_API_KEY` 或 `OPENAI_API_KEY`**（脚本内通过环境变量读取），并保证网络可访问智谱图像接口。

## 要点

* 自定义 `FlowToolCall` 子类：实现 `name`、`description`、`parameters` 及在 sandbox 中执行的 `__call__(session, arguments)`。
* `flow.Agent(..., tools=[ImageGenTool()])` 将工具暴露给模型。

## 源码

* [GitHub：`example/custom_tool_usage.py`](https://github.com/Rath-Team/OpenRath/blob/main/example/custom_tool_usage.py)

## 延伸阅读

* [工具](../user_guide/tools.md)
* [API：`rath.flow.tool`](../reference/flow_tool.md)

---

[← 示例索引](index.md)
