# Installation

OpenRath targets **CPython 3.10 through 3.13** (see `requires-python` in
`pyproject.toml`). Install the core package from the repository root that
contains `pyproject.toml`.

## Core install

From a checkout:

```bash
cd OpenRath
uv sync
# or: pip install -e .
```

Runtime dependencies are minimal: `openai` and `python-dotenv`.

## Optional: OpenSandbox backends

Isolated execution via OpenSandbox is shipped as an **optional extra**:

```bash
uv pip install -e ".[opensandbox]"
# or: pip install -e ".[opensandbox]"
```

That pulls `opensandbox`, `opensandbox-code-interpreter`, and `opensandbox-server`.
You still need a running sandbox server and compatible configuration on your host.

## Environment variables

Copy `.env.example` to `.env` and set at least:

| Variable | Role |
|----------|------|
| `OPENAI_API_KEY` | API key for OpenAI or a compatible gateway |
| `OPENAI_BASE_URL` | Chat completions base URL (default OpenAI v1) |
| `OPENAI_DEFAULT_MODEL` | Default model id when code omits `model` |

For OpenSandbox clients, see `.env.example` for `OPEN_SANDBOX_DOMAIN`,
`OPEN_SANDBOX_API_KEY`, and server-side key mirrors.

## Documentation build

Install doc dependencies and build static HTML:

```bash
uv sync --group dev --group docs
uv run sphinx-build -M html docs/source docs/_build
```

Output is written to `docs/_build/html/` and can be deployed to any static host.
