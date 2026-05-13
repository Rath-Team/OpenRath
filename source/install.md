# Installation

OpenRath supports CPython `3.10` through `3.13`. Choose the installation path that matches your use case:

| Goal | Path |
| --- | --- |
| Use OpenRath to build agent workflows | [Install OpenRath from PyPI](#install-openrath-from-pypi) |
| Modify OpenRath source, run tests, or build docs | [Install from source for development](#install-from-source-for-development) |
| Use a container sandbox backend | [Launch and connect OpenSandbox](#launch-and-connect-opensandbox) |

(install-openrath-from-pypi)=
## Install OpenRath from PyPI
This is the user installation path. It installs the OpenRath core runtime: `Session`, `Workflow`, `FlowToolCall`, the local backend, and the default OpenAI-compatible LLM client.

```bash
pip install openrath
```

If you manage your project environment with `uv`:

```bash
uv add openrath
```

Core dependencies include:

| Dependency | Purpose |
| --- | --- |
| `openai` | Default OpenAI-compatible chat client. |
| `pydantic` | Tool schemas, request/response models, and configuration types. |

### Configure the LLM
Real LLM workflows require OpenAI-compatible configuration. The core library keeps this explicit: build a `Provider` with the API key, optional base URL, and model. The repository examples include small helpers that read these values from process environment variables.

```bash
export OPENAI_API_KEY=...
export OPENAI_BASE_URL=https://api.openai.com/v1
export OPENAI_DEFAULT_MODEL=gpt-5.5
```

| Variable | Meaning |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI or compatible gateway API key. The default client fails if this is missing. |
| `OPENAI_BASE_URL` | OpenAI-compatible endpoint. |
| `OPENAI_DEFAULT_MODEL` | Model used by the repository example helpers when no role-specific model is set. |

If you also cloned the OpenRath repository, you can first run examples that do not depend on OpenSandbox:

```bash
python example/session_usage.py
python example/sandbox_backend_local.py
```

When using OpenRath from PyPI in your own project, import it directly:

```python
import os

from rath import flow
from rath.llm import Provider
from rath.session import Session

provider = Provider(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ.get("OPENAI_BASE_URL") or None,
    model=os.environ.get("OPENAI_DEFAULT_MODEL") or "gpt-5.5",
)

agent = flow.Agent("Use tools when helpful.", provider=provider)
user = Session.from_user_message("List files.").to("local", spec=".")
out = agent(user)
```

(install-from-source-for-development)=
## Install from source for development
This is the developer installation path. Use it to modify OpenRath source, run tests, build docs, or debug examples.

```bash
git clone https://github.com/Rath-Team/OpenRath.git
cd OpenRath
uv sync --group dev --group docs
```

Without `uv`, use an editable install:

```bash
pip install -e .
pip install pytest flake8 mypy sphinx myst-parser pydata-sphinx-theme
```

Development dependencies include:

| Dependency group | Contents |
| --- | --- |
| runtime | `openai`, `pydantic`. |
| dev | `pytest`, `flake8`, `mypy`. |
| docs | `sphinx`, `myst-parser`, `pydata-sphinx-theme`. |

Copy the environment template:

```bash
cp .env.example .env
```

Run tests:

```bash
bash scripts/run_openrath_test.sh
```

Build the docs:

```bash
bash scripts/build_docs.sh
```

Or call Sphinx directly:

```bash
uv run sphinx-build -M html docs/source docs/_build
```

The generated output is under `docs/_build/html/`.

(launch-and-connect-opensandbox)=
## Launch and connect OpenSandbox
OpenSandbox is an optional backend. It is useful for workflows that need a container execution environment. OpenRath connects to it with `Session.to("opensandbox", spec=...)`; the default local backend does not require this step.

### Install the OpenSandbox extra
When using PyPI:

```bash
pip install "openrath[opensandbox]"
```

When using a source development environment:

```bash
uv sync --extra opensandbox
```

This extra installs:

| Package | Purpose |
| --- | --- |
| `opensandbox` | OpenSandbox Python SDK. |
| `opensandbox-code-interpreter` | Code interpreter client. |
| `opensandbox-server` | Starts the OpenSandbox API server locally. |

### Start the service
Local development usually starts OpenSandbox with the repository script. The script checks Docker, syncs the optional dependency, generates `.sandbox.toml`, adds the current OpenRath project directory to the host bind allowlist, and starts `opensandbox-server`. On macOS with Colima, if `DOCKER_HOST` is unset and the Colima socket exists, the script exports `DOCKER_HOST=unix://${HOME}/.colima/default/docker.sock` automatically.

macOS / Linux:

```bash
bash scripts/launch_opensandbox.sh
```

Windows:

```bat
scripts\launch_opensandbox.bat
```

The script uses the OpenSandbox Docker configuration example by default. Switch the packaged example with an environment variable:

```bash
SANDBOX_INIT_EXAMPLE=docker bash scripts/launch_opensandbox.sh
```

Allowed values include `docker`, `docker-zh`, `k8s`, and `k8s-zh`.

### Check service status
After the OpenSandbox server starts, first check that the control plane responds. `/health` is the unauthenticated health-check path for the OpenSandbox server.

```bash
curl -fsS http://127.0.0.1:8080/health
```

If `curl` is not installed, use Python for the same check:

```bash
python - <<'PY'
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=3) as resp:
    print(resp.status)
    print(resp.read().decode("utf-8", errors="replace"))
PY
```

The health check only confirms that the OpenSandbox API server responds locally. The container runtime, workspace bind, and OpenRath client configuration still need to be verified with the later example.

### Connect OpenRath to OpenSandbox
Set client variables in the environment where OpenRath runs:

```bash
export OPEN_SANDBOX_DOMAIN=127.0.0.1:8080
export OPEN_SANDBOX_API_KEY=
```

If the server sets an API key, the server and client values must match:

```bash
export OPENSANDBOX_SERVER_API_KEY=...
export OPEN_SANDBOX_API_KEY=...
```

| Variable | Meaning |
| --- | --- |
| `OPEN_SANDBOX_DOMAIN` | OpenSandbox API server address. The local default is `127.0.0.1:8080`. |
| `OPEN_SANDBOX_API_KEY` | API key used by the OpenRath client when requesting the server. |
| `OPENSANDBOX_SERVER_API_KEY` | API key on the OpenSandbox server side. |
| `RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND` | When set to `1`, a failed host bind does not fall back to an empty workspace. |

### Verify the backend
After confirming that the server is listening locally, run the OpenSandbox example:

```bash
python example/sandbox_backend_opensandbox.py
```

You can also bind directly in Python:

```python
from rath.session import Session

user = Session.from_user_message("List the workspace.")
user = user.to("opensandbox", spec=".")
```

`spec="."` requests a bind from the current directory to `/workspace` inside the container. This host path must be visible to the machine running the OpenSandbox server and allowed by the storage allowlist in `.sandbox.toml`. The repository script automatically allowlists the current project directory. To bind other directories, manually add the matching prefix to `allowed_host_paths`. If the host bind is rejected, OpenRath retries with an empty workspace by default. Set `RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND=1` to disable this fallback.

## Local sandbox path notes
`Session.to("local", spec="...")` treats the string `spec` as `BackendSandboxSpec(working_dir=...)`. `LocalBackend.close(...)` only deletes temporary working directories that OpenRath created itself. User-supplied working directories are left on disk when the sandbox closes.
