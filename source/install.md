# 安装

OpenRath 支持 CPython `3.10` 到 `3.13`。根据你的目标选择安装路径：

| 目标 | 使用路径 |
| --- | --- |
| 只想使用 OpenRath 构建 agent workflow | [从 PyPI 安装 OpenRath](#install-openrath-from-pypi) |
| 想修改 OpenRath 源码、运行测试或构建文档 | [从源码安装开发环境](#install-from-source-for-development) |
| 想使用容器 sandbox backend | [启动并连接 OpenSandbox](#launch-and-connect-opensandbox) |

(install-openrath-from-pypi)=
## 从 PyPI 安装 OpenRath（Install OpenRath from PyPI）

这是面向使用者的安装方式。它安装 OpenRath 的核心 runtime：`Session`、`Workflow`、`FlowToolCall`、local backend 和默认 OpenAI-compatible LLM client。

```bash
pip install openrath
```

如果你使用 `uv` 管理项目环境：

```bash
uv add openrath
```

核心依赖包括：

| 依赖 | 用途 |
| --- | --- |
| `openai` | 默认 OpenAI-compatible chat client。 |
| `pydantic` | tool schema、request/response 和配置类型。 |
| `python-dotenv` | 从 `.env` 加载 LLM 与 backend 配置。 |

### 配置 LLM（Configure LLM settings）

真实 LLM workflow 需要 OpenAI-compatible 配置。OpenRath 会先尝试读取当前项目根目录的 `.env`，再读取进程环境变量。

```bash
export OPENAI_API_KEY=...
export OPENAI_BASE_URL=https://api.openai.com/v1
export OPENAI_DEFAULT_MODEL=gpt-5.5
```

| 变量 | 含义 |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI 或兼容网关 API key；缺失时默认客户端会报错。 |
| `OPENAI_BASE_URL` | OpenAI-compatible endpoint。 |
| `OPENAI_DEFAULT_MODEL` | 当 `Provider(model=None)` 时使用的默认模型。 |

如果你同时克隆了 OpenRath 仓库，可以先运行不依赖 OpenSandbox 的 examples：

```bash
python example/session_usage.py
python example/sandbox_backend_local.py
```

如果你是通过 PyPI 在自己的项目中使用 OpenRath，可以直接从你的项目代码里导入：

```python
from rath import flow
from rath.session import Session

agent = flow.Agent("Use tools when helpful.", model="gpt-5.5")
user = Session.from_user_message("List files.").to("local")
out = agent(user)
```

(install-from-source-for-development)=
## 从源码安装开发环境（Install from source for development）

这是面向开发者的安装方式。使用它来修改 OpenRath 源码、运行测试、构建 docs，或调试 examples。

```bash
git clone https://github.com/Rath-Team/OpenRath.git
cd OpenRath
uv sync --group dev --group docs
```

如果你不用 `uv`，可以使用 editable install：

```bash
pip install -e .
pip install pytest flake8 mypy sphinx myst-parser pydata-sphinx-theme
```

开发依赖包括：

| 依赖组 | 内容 |
| --- | --- |
| runtime | `openai`、`pydantic`、`python-dotenv`。 |
| dev | `pytest`、`flake8`、`mypy`。 |
| docs | `sphinx`、`myst-parser`、`pydata-sphinx-theme`。 |

复制环境变量模板：

```bash
cp .env.example .env
```

运行测试：

```bash
bash scripts/run_openrath_test.sh
```

构建文档：

```bash
bash scripts/build_docs.sh
```

或直接调用 Sphinx：

```bash
uv run sphinx-build -M html docs/source docs/_build
```

生成结果位于 `docs/_build/html/`。

(launch-and-connect-opensandbox)=
## 启动并连接 OpenSandbox（Launch and connect OpenSandbox）

OpenSandbox 是可选 backend。它适合需要容器执行环境的 workflow。OpenRath 通过 `Session.to("opensandbox", spec=...)` 连接它；默认 local backend 不需要这一步。

### 安装 OpenSandbox extra（Install OpenSandbox extra）

如果你从 PyPI 使用：

```bash
pip install "openrath[opensandbox]"
```

如果你在源码开发环境中使用：

```bash
uv sync --extra opensandbox
```

这个 extra 会安装：

| 包 | 用途 |
| --- | --- |
| `opensandbox` | OpenSandbox Python SDK。 |
| `opensandbox-code-interpreter` | code interpreter client。 |
| `opensandbox-server` | 本地启动 OpenSandbox API server。 |

### 启动服务（Start the server）

本地开发推荐使用仓库脚本。它会检查 Docker、同步 optional dependency、生成 `.sandbox.toml`，然后启动 `opensandbox-server`。

macOS / Linux:

```bash
bash scripts/launch_opensandbox.sh
```

Windows:

```bat
scripts\launch_opensandbox.bat
```

脚本默认使用 OpenSandbox 的 Docker 配置示例。可通过环境变量切换 packaged example：

```bash
SANDBOX_INIT_EXAMPLE=docker bash scripts/launch_opensandbox.sh
```

可选值包括 `docker`、`docker-zh`、`k8s`、`k8s-zh`。

### 检查服务状态（Health Check）

OpenSandbox server 启动后，先检查 control plane 是否响应。`/health` 是 OpenSandbox server 的免鉴权健康检查路径。

```bash
curl -fsS http://127.0.0.1:8080/health
```

如果你没有安装 `curl`，可以使用 Python 做同样的检查：

```bash
python - <<'PY'
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=3) as resp:
    print(resp.status)
    print(resp.read().decode("utf-8", errors="replace"))
PY
```

健康检查只说明 OpenSandbox API server 已经在本地响应。容器 runtime、workspace bind 和 OpenRath client 配置还需要通过后面的 example 验证。

### 连接 OpenRath 与 OpenSandbox（Connect OpenRath to OpenSandbox）

在运行 OpenRath 的环境中设置客户端变量：

```bash
export OPEN_SANDBOX_DOMAIN=127.0.0.1:8080
export OPEN_SANDBOX_API_KEY=
```

如果 server 设置了 API key，服务端和客户端需要一致：

```bash
export OPENSANDBOX_SERVER_API_KEY=...
export OPEN_SANDBOX_API_KEY=...
```

| 变量 | 含义 |
| --- | --- |
| `OPEN_SANDBOX_DOMAIN` | OpenSandbox API server 地址，默认本地为 `127.0.0.1:8080`。 |
| `OPEN_SANDBOX_API_KEY` | OpenRath client 请求 server 使用的 API key。 |
| `OPENSANDBOX_SERVER_API_KEY` | OpenSandbox server 侧 API key。 |
| `RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND` | 设为 `1` 时，host bind 失败不降级为空 workspace。 |

### 验证 backend（Verify the backend）

确认 server 在本地监听后，运行 OpenSandbox example：

```bash
python example/sandbox_backend_opensandbox.py
```

也可以在 Python 中直接绑定：

```python
from rath.session import Session

user = Session.from_user_message("List the workspace.")
user = user.to("opensandbox", spec=".")
```

`spec="."` 会请求把当前目录绑定到容器内 `/workspace`。该 host path 必须对 OpenSandbox server 所在机器可见，并且需要被 `.sandbox.toml` 的 storage allowlist 允许。若 host bind 被拒绝，OpenRath 默认会重试为空 workspace；设置 `RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND=1` 可以关闭这个降级。

## 本地沙箱路径说明（Local sandbox path note）

`Session.to("local", spec="...")` 会把字符串 `spec` 当作 `BackendSandboxSpec(working_dir=...)`。当前 `LocalBackend.close(...)` 会删除它管理的 working directory；因此正式调试时更建议使用临时目录或可重建目录。若绑定项目根目录，只适合明确知道生命周期的短期实验。
