(example-session-usage)=
# Session 用法示例

对应脚本：`example/session_usage.py`。

本示例把几个基础原语放在同一个文件里：创建 agent session、创建 user session、`fork()`、`detach()`、绑定 local backend、运行 `run_session_loop(...)`，最后用 `run_session_compress(...)` 压缩上下文。

## 覆盖内容
| 主题 | 结果 |
| --- | --- |
| agent session | system prompt 作为单独 session 存在。 |
| user session | 用户输入作为 user-side session 存在。 |
| fork 与 detach | session 可以复制内容，也可以切断 lineage。 |
| backend placement | `.to("local", spec="./")` 决定工具执行位置。 |
| loop 与 compress | 一次 agent loop 之后可以继续压缩 session。 |

## 关键代码
```python
from rath import flow
from rath.session import Session, run_session_loop, run_session_compress

agent_session = Session.from_agent_prompt("You are a helpful assistant.")
user_session = Session.from_user_message(
    "Please use tool to summarize this workspace. And return the summary."
)
user_session = user_session.to("local", spec="./")

provider = flow.Provider(model="glm-5.1")
out_session = run_session_loop(
    user_session=user_session,
    agent_session=agent_session,
    agent_provider=provider,
)

compressed = run_session_compress(
    user_session=out_session,
    agent_session=agent_session,
    agent_provider=provider,
)
```

## 关键行解释
| 行 | 解释 |
| --- | --- |
| `Session.from_agent_prompt(...)` | 创建 agent-side system session。 |
| `Session.from_user_message(...)` | 创建 user-side session。 |
| `.to("local", spec="./")` | 把当前项目目录作为 local workspace。 |
| `run_session_loop(...)` | 拼接 agent session 和 user session，允许模型调用工具。 |
| `run_session_compress(...)` | 把已有 transcript 压缩成新的 user-only session。 |

## 运行
```bash
python example/session_usage.py
```

该脚本需要真实 LLM 配置。模型名来自项目配置；缺省时使用脚本里的默认值。

## 观察结果
| 位置 | 看什么 |
| --- | --- |
| 第一次 `print(out_session)` | loop 后的 session，包含 assistant rows 和可能的 tool result rows。 |
| 第二次 `print(out_session)` | compress 后的新 session，通常更短，并包含新的 user-side summary。 |
| workspace | 如果模型调用内置工具，工具会在绑定目录中执行。 |

## 常见问题
| 现象 | 检查方向 |
| --- | --- |
| LLM 请求失败 | 检查 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、模型名。 |
| 工具无法访问文件 | 检查 `.to("local", spec="./")` 指向的目录。 |
| compress 报空输出 | 检查模型是否返回了非空 assistant content。 |
| 输出很长 | 这是 loop 的原始 transcript；压缩结果应在第二次输出中查看。 |

## 练习
1. 把 `spec="./"` 改成一个临时目录，观察模型能看到的文件变化。
2. 在 loop 前调用 `fork()`，分别让两个 session 执行不同任务。
3. 改写 compress prompt，让压缩结果保留 TODO 列表。
