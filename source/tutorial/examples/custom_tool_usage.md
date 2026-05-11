(example-custom-tool)=
# 自定义工具示例

对应脚本：`example/custom_tool_usage.py`。

本示例把智谱 GLM-Image API 包装成 `FlowToolCall`，说明外部 HTTPS 服务如何变成模型可调用的工具。

## 覆盖内容
| 主题 | 结果 |
| --- | --- |
| schema 定义 | `ImageGenInput` 约束 prompt 和 size。 |
| tool class | `ImageGenTool` 同时提供名称、说明、参数和执行逻辑。 |
| 外部 API | 工具在 Python runtime 中发起 HTTPS 请求。 |
| agent 注册 | `flow.Agent(..., tools=[ImageGenTool()])` 把工具交给 loop。 |
| 结果回传 | API JSON 会作为工具返回值进入 `tool_result`。 |

## 工具代码
```python
class ImageGenTool(FlowToolCall):
    @property
    def name(self) -> str:
        return "image_gen"

    @property
    def description(self) -> str | None:
        return (
            "Generate an image with Zhipu GLM-Image. "
            "Returns parsed API JSON."
        )

    @property
    def parameters(self) -> Mapping[str, Any]:
        return dict(ImageGenInput.model_json_schema())

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> dict[str, Any]:
        model = ImageGenInput.model_validate(dict(arguments or {}))
        ...
        return json.loads(raw)
```

## 关键行解释
| 行 | 解释 |
| --- | --- |
| `ImageGenInput.model_json_schema()` | 生成模型可见的 JSON Schema。 |
| `model_validate(...)` | 校验模型返回的 arguments。 |
| `urllib.request.Request(...)` | 在工具内部调用外部服务。 |
| `return json.loads(raw)` | 返回普通 dict，loop 会序列化成 `tool_result`。 |
| `tools=[ImageGenTool()]` | 让 agent 在 loop 中能看到 `image_gen`。 |

## 运行
```bash
export ZHIPU_API_KEY=...
python example/custom_tool_usage.py
```

也可以使用 `OPENAI_API_KEY` 作为 fallback。真实 key 应保存在环境变量、本地 `.env` 或密钥管理系统中，不写入教程、脚本或仓库提交。

## 观察结果
| 位置 | 看什么 |
| --- | --- |
| stdout | 输出 session 里应包含工具调用后的 assistant 回复。 |
| tool result | 应包含图像 API 返回的 JSON。 |
| 最终回复 | agent 应从工具结果中提取图片 URL 或说明。 |

脚本里的 user prompt 提到了保存图片文件，但当前 `ImageGenTool` 只返回 API JSON；如果要真的下载图片，需要再实现一个下载或文件写入工具。

## 常见问题
| 现象 | 检查方向 |
| --- | --- |
| `Set ZHIPU_API_KEY or OPENAI_API_KEY` | 没有配置图像 API key。 |
| HTTP error | 检查 key、额度、模型名和图片尺寸。 |
| 模型不调用工具 | 检查 system prompt 是否明确要求调用 `image_gen`。 |
| 返回 JSON 里没有 URL | 先打印 tool result，确认外部 API 返回结构。 |

## 练习
1. 给 `ImageGenInput` 增加 `style` 参数，并拼接进 prompt。
2. 把工具改成只返回 `data[0].url`，减少模型需要解析的内容。
3. 增加一个文件下载工具，把 URL 下载到 sandbox workspace。
