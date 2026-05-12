(example-sandbox-local)=
# 如何绑定本地沙箱

对应脚本：`example/sandbox_backend_local.py`。

本地沙箱使用 `LocalBackend`，工具调用会在主机上以子进程/文件系统方式执行。

```python
from rath.session import Session

user_session = Session.from_user_message(
    "List all files in the current directory. And summarize the result."
)

user_session = user_session.to("local", spec=None)
out_session = agent(user_session)

user_session = user_session.to("local", spec=".")
out_session = agent(user_session)
```

## 两种工作目录

| 写法 | 行为 |
| --- | --- |
| `spec=None` | `LocalBackend` 创建临时目录，通常是空 workspace。 |
| `spec="..."` | 字符串被解释为 `BackendSandboxSpec(working_dir=...)`。 |

## 注意

当前 `LocalBackend.close(...)` 会删除 sandbox handle 指向的目录。绑定 `spec="."` 可以演示项目目录访问，但不适合作为长期安全默认值。更稳妥的做法是绑定临时目录或副本目录。

## 运行

```bash
python example/sandbox_backend_local.py
```

需要 `.env` 中的 LLM 配置，因为脚本会通过 `flow.Agent` 发起真实补全。

[GitHub：`example/sandbox_backend_local.py`](https://github.com/Rath-Team/OpenRath/blob/main/example/sandbox_backend_local.py)
