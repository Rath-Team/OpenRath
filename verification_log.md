# OpenRath Docs 验证记录

本文记录中文站开发期间做过的本地验证。记录只保留命令意图、关键结果和阻塞项，不记录任何真实 API key。

## 2026-05-11

### 本地测试集
环境：`mamba run -n rath-dev`

命令意图：运行不依赖真实 LLM 的单元、session、flow、backend、conformance 测试。

结果：

```text
226 passed, 40 skipped in 2.17s
```

覆盖范围：

| 范围 | 结果 |
| --- | --- |
| `tests/unit` | 通过 |
| `tests/flow` | 通过 |
| `tests/session` | 通过 |
| `tests/backends` | 通过，OpenSandbox real server 相关测试跳过 |
| `tests/conformance` | 通过，依赖 unavailable backend 的参数化用例跳过 |
| `tests/test_import.py` | 通过 |

### DeepSeek 兼容网关
环境变量：

```text
OPENAI_API_KEY
OPENAI_BASE_URL
OPENAI_DEFAULT_MODEL=deepseek-chat
```

命令意图：通过 OpenAI-compatible client 发起一次真实 chat completion。

结果：

```text
model: deepseek-v4-flash
finish_reason: stop
contains_marker: True
```

命令意图：通过 `run_session_loop(...)` 运行一次真实 session loop，并继续调用 `run_session_compress(...)`。

结果：

```text
loop_contains_marker: True
sandbox_migrated: True
compress_contains_marker: True
compressed_rows: 1
```

结论：当前 OpenAI-compatible client、`run_session_loop(...)`、local backend sandbox 迁移和 `run_session_compress(...)` 可以使用 DeepSeek 兼容网关跑通最小端到端路径。

### OpenSandbox
环境：`rath-dev` 中已安装 `opensandbox` 包，Docker runtime 使用 Colima。

backend registry 检查：

```text
local registered available= True
opensandbox registered available= True
```

服务健康检查：

```text
{"status":"healthy"}
```

调通过程：

| 问题 | 处理 |
| --- | --- |
| Docker daemon 未运行 | 启动 Colima。 |
| `opensandbox-server` 找不到 Colima socket | 启动 server 时设置 `DOCKER_HOST=unix://${HOME}/.colima/default/docker.sock`，并把该逻辑写入启动脚本。 |
| 首次创建 sandbox 超时 | 预拉 `opensandbox/code-interpreter:v1.0.2`、`opensandbox/execd:v1.0.14`、`opensandbox/egress:v1.0.10`。 |
| `spec="."` host bind 被拒绝 | 将 `/Users/kk/Project/OpenRath` 加入 `.sandbox.toml` 的 `allowed_host_paths`。 |

最小 backend 验证结果：

```text
available: True
cmd_exit: 0
cmd_stdout: /workspaceOPENRATH_OSB_CMD_OK
write_bytes: 20
read_data: OPENRATH_OSB_FILE_OK
code_stdout: OPENRATH_OSB_CODE_OK
code_error: None
```

严格 host bind 验证结果：

```text
exit: 0
stdout: /workspaceOPENRATH_OSB_BIND_OK
```

OpenSandbox example 使用 DeepSeek 兼容网关运行通过：

```text
python example/sandbox_backend_opensandbox.py
```

观察结果：`spec=None` 阶段显示空 workspace；`spec="."` 阶段成功列出 OpenRath 仓库目录。

相关测试：

```text
17 passed in 16.90s
```

### Trading Agents key 行为
命令意图：在没有设置 `ALPHA_VANTAGE_API_KEY` 的情况下运行 Trading Agents CLI，确认示例不会使用默认行情 key。

结果：

```text
ERROR: ALPHA_VANTAGE_API_KEY is required.
```

结论：Trading Agents 示例现在要求用户显式设置自己的 Alpha Vantage key。
