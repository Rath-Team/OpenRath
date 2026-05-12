(example-custom-tool)=
# Custom Tool Usage

Script: `example/custom_tool_usage.py`.

This script shows how to connect an external HTTPS service: wrap the Zhipu GLM-Image API as a `FlowToolCall`, let the model call it through the tool schema, and run the actual request in the Python runtime.

## What it covers
| Topic | Result |
| --- | --- |
| schema definition | `ImageGenInput` constrains the prompt and size. |
| tool class | `ImageGenTool` provides the name, description, parameters, and execution logic. |
| external API | The tool sends the HTTPS request in the Python runtime. |
| agent registration | `flow.Agent(..., tools=[ImageGenTool()])` passes the tool to the loop. |
| returned result | The API JSON enters the session as a `tool_result`. |

## Tool code
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

## Key lines
| Line | Explanation |
| --- | --- |
| `ImageGenInput.model_json_schema()` | Generates the JSON Schema visible to the model. |
| `model_validate(...)` | Validates the arguments returned by the model. |
| `urllib.request.Request(...)` | Calls the external service inside the tool. |
| `return json.loads(raw)` | Returns a plain dict, which the loop serializes into a `tool_result`. |
| `tools=[ImageGenTool()]` | Makes `image_gen` available to the agent in the loop. |

## Run
```bash
export ZHIPU_API_KEY=...
python example/custom_tool_usage.py
```

You can also use `OPENAI_API_KEY` as a fallback. Store real keys in environment variables, a local `.env`, or a secrets manager, not in tutorials, scripts, or commits.

## Successful output
The script prints a `Session(...)`. On success, the chunk table contains one `image_gen` tool call and its `tool_result`; the final assistant reply references the image URL or generation summary returned by the tool.

```text
Session(
  chunks=[
    [0] user: 'Generate a simple cartoon cat on a sofa...'
    [1] assistant: tools=[image_gen(...)]
    [2] tool_result: name='image_gen', body='{"created": ... , "data": ...}'
    [3] assistant: text='Generated image: https://...'
  ]
)
```

The current tool only returns the API JSON. It does not download image files. Seeing a URL does not mean a local file was saved.

## What to inspect
| Location | What to check |
| --- | --- |
| stdout | The output session should include the assistant reply after the tool call. |
| tool result | Should contain the JSON returned by the image API. |
| final reply | The agent should extract the image URL or summary from the tool result. |

The user prompt in the script mentions saving an image file, but the current `ImageGenTool` only returns API JSON. To actually download the image, add a download or file-writing tool.

## Troubleshooting
| Symptom | Check |
| --- | --- |
| `Set ZHIPU_API_KEY or OPENAI_API_KEY` | No image API key is configured. |
| HTTP error | Check the key, quota, model name, and image size. |
| Model does not call the tool | Check whether the system prompt clearly asks for `image_gen`. |
| Returned JSON has no URL | Print the tool result first and confirm the external API response shape. |

## Exercises
1. Add a `style` parameter to `ImageGenInput` and append it to the prompt.
2. Change the tool to return only `data[0].url`, reducing what the model must parse.
3. Add a file download tool that downloads the URL into the sandbox workspace.
