# OpenRath 中文站发布前审计

本文记录中文站当前发布前审计结果。审计目标是发现影响预览、学习路径和开源可信度的问题。

## 2026-05-11

### 构建
命令意图：构建中文站 HTML。

结果：

```text
build succeeded
```

输出目录：

```text
docs/_build/html
```

### 链接
命令意图：运行 Sphinx linkcheck。

结果：

```text
build succeeded
```

处理过的问题：

| 问题 | 处理 |
| --- | --- |
| 示例页底部手写 GitHub 源码链接在私有仓库或 docs 分支预览时返回 404 | 改成本地源码路径，例如 `example/session_usage.py`。 |

### 搜索
命令意图：确认静态搜索使用自定义 mixed tokenizer，并包含中文同义词。

结果：

| 查询意图 | 已覆盖词 |
| --- | --- |
| 会话 | `会话`、`上下文`、`session` |
| 工具 | `工具`、`tool` |
| 沙箱 | `沙箱`、`sandbox`、`opensandbox` |
| 多智能体 | `多智能体`、`multiagent`、`multi`、`agent` |
| 安装 | `安装`、`install`、`installation` |

### 文案风格
命令意图：检查中文站源文件中是否残留中英括号混排标题和否定式对比句。

结果：未发现残留。

检查范围：

```text
docs/source
docs/README.md
docs/site_decisions.md
docs/content_milestones.md
docs/verification_log.md
```

### Secret 与默认 key
命令意图：检查文档和源码中是否残留明显 key 字符串或 Trading Agents 默认 Alpha Vantage key。

结果：未发现残留。

处理过的问题：

| 问题 | 处理 |
| --- | --- |
| `example/trading_agents` 默认使用 Alpha Vantage demo key | 改为要求显式设置 `ALPHA_VANTAGE_API_KEY`。 |
| 文档可能暴露真实 key | 文档只保留环境变量名和占位符。 |

### OpenSandbox
命令意图：检查 OpenSandbox 安装页和 Developer Notes 是否有健康检查说明。

结果：

| 页面 | 状态 |
| --- | --- |
| `docs/source/install.md` | 已包含 `/health` 检查和 Python health check。 |
| `docs/source/developer_notes/sandbox.md` | 已包含 health check 与 example 验证路径。 |
| `docs/source/tutorial/examples/sandbox_backend_opensandbox.md` | 已包含前置条件、健康检查和失败检查。 |

本机验证：

```text
OpenSandbox backend registered and available.
Health check passed.
spec=None and spec="." example paths passed.
```

### GitHub edit branch
`docs/source/conf.py` 中的 edit branch 已指向 `docs`：

```python
html_context = {
    "github_version": "docs",
}
```

发布到 main 后，可以按发布策略再切回目标发布分支。
