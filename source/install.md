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

运行时依赖极少：`openai` 与 `pydantic`。

## 可选：OpenSandbox 后端

通过 OpenSandbox 进行隔离执行时，使用 **可选 extra** 安装：

```bash
uv pip install -e ".[opensandbox]"
# 或: pip install -e ".[opensandbox]"
```

会拉取 `opensandbox`、`opensandbox-code-interpreter`、`opensandbox-server`。你仍须在本机运行兼容的沙箱服务并完成配置。

## 环境变量（自助配置）

OpenRath **不会**读取仓库中的 `.env` 文件。请在 Shell、IDE 启动配置或容器编排中自行导出变量，或在代码里构造 `rath.llm.Provider`。

常见 **OpenAI 兼容**网关变量：

| 变量 | 作用 |
|------|------|
| `OPENAI_API_KEY` | API 密钥（必填才能使用默认 `RathOpenAIChatClient`） |
| `OPENAI_BASE_URL` | Chat Completions 基址（可选） |
| `OPENAI_DEFAULT_MODEL` | 可自行读入并传给 `Provider.model`（可选） |

OpenSandbox 客户端常用：`OPEN_SANDBOX_DOMAIN`、`OPEN_SANDBOX_API_KEY` 等（依你的部署文档）。

## 构建本文档

安装文档依赖并生成静态 HTML：

```bash
uv sync --group dev --group docs
uv run sphinx-build -M html docs/source docs/_build
```

输出位于 `docs/_build/html/`，可部署到任意静态站点。

代码仓库：[https://github.com/Rath-Team/OpenRath](https://github.com/Rath-Team/OpenRath)。
