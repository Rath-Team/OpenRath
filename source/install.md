# 安装

OpenRath 面向 **CPython 3.10—3.13**（见 `pyproject.toml` 中的 `requires-python`）。请在包含 `pyproject.toml` 的仓库根目录安装。

文档结构便于对照常见科学 Python 项目：**先装核心、再装可选扩展、最后说明如何构建本手册**。上游打包文档可参考 [PyTorch 安装指引](https://pytorch.org/get-started/locally/)，区分**运行环境安装**与**文档构建**。

## 核心安装

在克隆的仓库中：

```bash
cd OpenRath
uv sync
# 或: pip install -e .
```

运行时依赖极少：`openai` 与 `python-dotenv`。

## 可选：OpenSandbox 后端

通过 OpenSandbox 进行隔离执行时，使用 **可选 extra** 安装：

```bash
uv pip install -e ".[opensandbox]"
# 或: pip install -e ".[opensandbox]"
```

会拉取 `opensandbox`、`opensandbox-code-interpreter`、`opensandbox-server`。你仍须在本机运行兼容的沙箱服务并完成配置。

## 环境变量

将 `.env.example` 复制为 `.env`，至少配置：

| 变量 | 作用 |
|------|------|
| `OPENAI_API_KEY` | OpenAI 或兼容网关的 API 密钥 |
| `OPENAI_BASE_URL` | Chat Completions 基址（默认 OpenAI v1 风格） |
| `OPENAI_DEFAULT_MODEL` | 代码未指定 `model` 时的默认模型 ID |

OpenSandbox 客户端相关变量见 `.env.example`（如 `OPEN_SANDBOX_DOMAIN`、`OPEN_SANDBOX_API_KEY` 及服务端密钥镜像）。

## 构建本文档

安装文档依赖并生成静态 HTML：

```bash
uv sync --group dev --group docs
uv run sphinx-build -M html docs/source docs/_build
```

输出位于 `docs/_build/html/`，可部署到任意静态站点。

代码仓库：[https://github.com/Rath-Team/OpenRath](https://github.com/Rath-Team/OpenRath)。
