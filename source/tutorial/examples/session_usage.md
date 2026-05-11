(example-session-usage)=
# 如何使用 Session

对应脚本：`example/session_usage.py`。

这个示例展示三件事：

1. 用 `Session.from_agent_prompt(...)` 构造 agent prompt；
2. 用 `Session.from_user_message(...)` 构造用户输入；
3. 先跑 `run_session_loop`，再跑 `run_session_compress`。

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

## 关键点

- `agent_session` 只作为 LLM 请求的前置上下文，不会被复制进输出 session 的 chunk table。
- `user_session.to("local", spec="./")` 让工具能访问指定工作目录。
- `run_session_loop` 会把 sandbox 从输入 session 转移到输出 session。
- `run_session_compress` 会用一次 LLM 请求生成新的 user-only session。

## 运行

```bash
python example/session_usage.py
```

该脚本需要真实 LLM key。模型名 `glm-5.1` 只是示例，应替换为你的兼容网关支持的模型。

[GitHub：`example/session_usage.py`](https://github.com/Rath-Team/OpenRath/blob/main/example/session_usage.py)
