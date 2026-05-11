(example-sandbox-opensandbox)=
# OpenSandbox 后端示例

对应脚本：`example/sandbox_backend_opensandbox.py`。

本示例展示同一段 agent 逻辑如何从 local backend 切到 OpenSandbox backend。核心入口仍然是 `Session.to(...)`，变化的是 backend 名称和服务端配置。

## 覆盖内容
| 主题 | 结果 |
| --- | --- |
| backend switch | `Session.to("opensandbox", spec=...)` 选择 OpenSandbox。 |
| service dependency | OpenSandbox backend 需要外部服务可访问。 |
| empty workspace | `spec=None` 对应容器内空的 `/workspace`。 |
| workspace bind | `spec="."` 会尝试把 host path 绑定到容器 workspace。 |
| strict mode | 绑定失败时可以选择重试空 workspace 或直接失败。 |

## 前置条件
1. 安装 OpenSandbox extra。
2. 启动兼容 OpenSandbox API 的服务。
3. 配置 OpenSandbox domain 和 API key。
4. 需要 host path bind 时，服务端 `allowed_host_paths` 允许对应路径。

示例命令：

```bash
pip install -e ".[opensandbox]"
export OPEN_SANDBOX_DOMAIN=http://127.0.0.1:8000
export OPEN_SANDBOX_API_KEY=...
```

先单独执行健康检查：

```bash
python - <<'PY'
import rath.backend as backend

b = backend.get("opensandbox")
print("available:", b.is_available())
print("capabilities:", b.capabilities())
PY
```

## 关键代码
```python
user_session = Session.from_user_message(
    "List all files in the current directory. And summarize the result."
)

user_session = user_session.to("opensandbox", spec=None)
out_session = agent(user_session)

user_session = user_session.to("opensandbox", spec=".")
out_session = agent(user_session)
```

## workspace bind 行为
| 写法 | 行为 |
| --- | --- |
| `spec=None` | 创建不绑定 host path 的 OpenSandbox workspace。 |
| `spec="."` | 尝试把当前目录绑定到容器 `/workspace`。 |
| strict mode off | host bind 被拒绝时，后端可以回退为空 workspace。 |
| strict mode on | host bind 被拒绝时直接失败。 |

仓库的 `scripts/launch_opensandbox.sh` 会把当前项目目录写入 `.sandbox.toml` 的 `allowed_host_paths`。手动启动 OpenSandbox，或把 `spec` 指向其他目录时，需要自己更新 allowlist。

如需严格失败：

```bash
export RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND=1
```

## 运行
```bash
python example/sandbox_backend_opensandbox.py
```

该脚本同时需要真实 LLM 配置和 OpenSandbox 服务配置。

## 观察结果
| 阶段 | 看什么 |
| --- | --- |
| availability check | `backend.get("opensandbox").is_available()` 为真时才运行 main。 |
| `spec=None` | agent 看到容器中的空 workspace。 |
| `spec="."` | 服务允许 bind 时，agent 能看到绑定目录内容。 |
| 回退行为 | 非 strict 模式下，bind 失败可能仍继续运行。 |

## 常见问题
| 现象 | 检查方向 |
| --- | --- |
| backend unavailable | 检查 extra、OpenSandbox SDK、环境变量。 |
| 服务连接失败 | 检查 `OPEN_SANDBOX_DOMAIN`、服务端端口、API key。 |
| host bind 被拒绝 | 检查服务端 allowed host paths。 |
| agent 看不到项目文件 | 确认 `spec="."` 阶段是否真的 bind 成功。 |

## 练习
1. 把 `spec="."` 改成 `.workspace/opensandbox-demo`。
2. 打开 strict mode，故意绑定一个未允许路径，观察错误。
3. 对比 local backend 与 OpenSandbox backend 的 `tool_result` 输出差异。
