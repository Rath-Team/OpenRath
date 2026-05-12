(example-custom-tool)=
# 如何自定义工具

对应脚本：`example/custom_tool_usage.py`。

自定义工具通过继承 `FlowToolCall` 实现。工具对象同时提供 LLM schema 和执行逻辑。

示例中的 `ImageGenTool`：

```python
class ImageGenTool(FlowToolCall):
    @property
    def name(self) -> str:
        return "image_gen"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return dict(ImageGenInput.model_json_schema())

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> dict[str, Any]:
        model = ImageGenInput.model_validate(dict(arguments or {}))
        ...
        return json.loads(raw)
```

## 关键点

- loop 会把解析后的 arguments 传给工具；示例里使用 `ImageGenInput.model_validate(...)` 做参数校验。
- 工具可以完全在 Python 进程内执行，也可以自己调用 `session.require_sandbox().dispatch(...)`。
- `flow.Agent(..., tools=[ImageGenTool()])` 会把工具传给 `run_session_loop`。
- 如果工具名与内置工具 `run_shell_command` 或 `write_workspace_file` 冲突，loop 会抛 `ToolNameConflictError`。

## 运行

```bash
python example/custom_tool_usage.py
```

该示例访问智谱 GLM-Image API，需要 `ZHIPU_API_KEY` 或 `OPENAI_API_KEY`。它展示如何把外部服务包装成 `FlowToolCall`。

[GitHub：`example/custom_tool_usage.py`](https://github.com/Rath-Team/OpenRath/blob/main/example/custom_tool_usage.py)
