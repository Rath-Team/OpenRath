(example-sandbox-opensandbox)=
# 如何绑定 OpenSandbox

对应脚本：`example/sandbox_backend_opensandbox.py`。

OpenSandbox 后端与本地后端使用同一个 `Session.to(...)` 入口，只是 backend 名称不同：

```python
user_session = Session.from_user_message(
    "List all files in the current directory. And summarize the result."
)

user_session = user_session.to("opensandbox", spec=None)
out_session = agent(user_session)

user_session = user_session.to("opensandbox", spec=".")
out_session = agent(user_session)
```

## 前置条件

1. 安装 extra：`pip install -e ".[opensandbox]"`。
2. 启动兼容 OpenSandbox API 服务。
3. 配置 `OPEN_SANDBOX_DOMAIN` 和 API key。
4. 若绑定 host path，服务端 `[storage].allowed_host_paths` 需要允许该路径。

## workspace bind 行为

当 `spec="."` 时，OpenRath 会尝试把 host path 绑定到容器中的 `/workspace`。如果服务拒绝 host bind，非 strict 模式会自动重试为空 workspace。

如需严格失败：

```bash
export RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND=1
```

## 运行

```bash
python example/sandbox_backend_opensandbox.py
```

[GitHub：`example/sandbox_backend_opensandbox.py`](https://github.com/Rath-Team/OpenRath/blob/main/example/sandbox_backend_opensandbox.py)
