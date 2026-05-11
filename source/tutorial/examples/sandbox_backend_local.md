(example-sandbox-local)=
# 本地后端示例

对应脚本：`example/sandbox_backend_local.py`。

本示例展示 `Session.to("local", spec=...)` 的两种用法：创建空的临时 workspace，或者绑定一个已有目录。它用于说明 local backend 的执行位置。

## 覆盖内容
| 主题 | 结果 |
| --- | --- |
| backend availability | 脚本先检查 local backend 是否可用。 |
| empty workspace | `spec=None` 会打开一个临时空目录。 |
| bound workspace | `spec="."` 会把项目目录作为 workspace。 |
| agent tool path | agent 调用内置工具时，会在当前 session 的 sandbox 中执行。 |
| close behavior | local backend 管理目录生命周期，绑定真实目录时要谨慎。 |

## 关键代码
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
| 写法 | 行为 | 适合场景 |
| --- | --- | --- |
| `spec=None` | local backend 创建临时目录。 | 验证工具能运行，不触碰项目文件。 |
| `spec="."` | 字符串被解释为 `BackendSandboxSpec(working_dir=".")`。 | 让工具读取当前项目目录。 |

## 运行
```bash
python example/sandbox_backend_local.py
```

需要配置真实 LLM，因为脚本会通过 `flow.Agent` 让模型决定是否调用工具。模型名来自项目配置；缺省时使用脚本里的默认值。

## 观察结果
| 阶段 | 看什么 |
| --- | --- |
| 初始输出 | `user_session.sandbox_backend` 一开始通常为空。 |
| `spec=None` | 模型看到的是临时空 workspace。 |
| `spec="."` | 模型可以列出当前项目目录内容。 |
| 最后一条 assistant row | 脚本打印 `out_session.chunk_table.rows[-1].payload["content"]`。 |

## 常见问题
| 现象 | 检查方向 |
| --- | --- |
| backend unavailable | 确认 core package 已安装，local backend 已注册。 |
| LLM 请求失败 | 检查模型网关配置。 |
| 文件列表为空 | 当前可能处在 `spec=None` 阶段。 |
| 工具访问了真实项目目录 | 确认当前运行的是 `spec="."` 阶段，并谨慎处理写入类请求。 |

## 练习
1. 把 `spec="."` 改成 `.workspace/local-demo`。
2. 修改 user prompt，让 agent 创建一个文件再读取。
3. 打印所有 `tool_result` row，观察命令输出如何进入 session。
