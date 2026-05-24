"""Fixtures for the OpenViking-backed memory-plane tests.

All tests under ``tests/memory/backends/`` run against a real OpenViking
server (``scripts/launch_openviking.sh``). They share three gates:

- **Collection-time SDK gate** — :data:`collect_ignore_glob` below skips
  every ``test_openviking_*.py`` module when the ``openviking`` optional
  extra is not installed, so pytest never tries to import those modules
  (which all do ``from rath.memory.adapters.openviking import
  OpenVikingBackend`` at the top, raising ``ModuleNotFoundError`` and
  failing collection without the extra).
- **Marker** — every test file in this directory is tagged
  ``pytest.mark.openviking`` via its own ``pytestmark``, so
  ``pytest -m 'not openviking'`` deselects them by marker alone.
- **Runtime canary fixture** — the autouse ``_openviking_canary``
  fixture below also skips the test when ``$OPEN_VIKING_URL/health`` is
  unreachable or ``OPEN_VIKING_ROOT_API_KEY`` is unset.
"""

from __future__ import annotations

import importlib.util
import json
import os
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

# Without the openviking SDK present, every ``test_openviking_*.py``
# under this directory would raise ``ModuleNotFoundError`` at collection
# time (their module top imports
# :class:`rath.memory.adapters.openviking.OpenVikingBackend`, which in
# turn imports the ``openviking`` SDK). ``collect_ignore_glob`` is the
# documented way to opt out of collection for a glob of files under a
# conftest — see pytest's reference for ``collect_ignore_glob``.
collect_ignore_glob: list[str] = []
if importlib.util.find_spec("openviking") is None:
    collect_ignore_glob.append("test_openviking_*.py")

_DEFAULT_URL = "http://127.0.0.1:1933"
_DEFAULT_CONF = Path.home() / ".openviking" / "ov.conf"


def _probe_health(url: str) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=2.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return bool(body.get("healthy")), ""
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    except json.JSONDecodeError as exc:
        return False, f"non-JSON /health response: {exc}"


def _resolve_root_api_key() -> str | None:
    env_key = os.environ.get("OPEN_VIKING_ROOT_API_KEY")
    if env_key:
        return env_key
    if _DEFAULT_CONF.is_file():
        try:
            data = json.loads(_DEFAULT_CONF.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data.get("server", {}).get("root_api_key")
    return None


@pytest.fixture(scope="session")
def openviking_url() -> str:
    return os.environ.get("OPEN_VIKING_URL", _DEFAULT_URL)


@pytest.fixture(scope="session")
def openviking_root_api_key() -> str:
    key = _resolve_root_api_key()
    if not key:
        pytest.fail(
            "OPEN_VIKING_ROOT_API_KEY is not set and ~/.openviking/ov.conf could not be "
            "read; export the key printed by scripts/launch_openviking.sh."
        )
    return key


@pytest.fixture(autouse=True)
def _openviking_canary() -> Iterator[None]:
    pytest.importorskip("openviking", reason="openviking optional extra not installed")
    url = os.environ.get("OPEN_VIKING_URL", _DEFAULT_URL)
    healthy, detail = _probe_health(url)
    if not healthy:
        pytest.skip(
            f"OpenViking server unreachable at {url}/health ({detail}); start it with "
            "`bash scripts/launch_openviking.sh`."
        )
    if not _resolve_root_api_key():
        pytest.skip(
            "OpenViking server is up but OPEN_VIKING_ROOT_API_KEY is not set and "
            "~/.openviking/ov.conf has no server.root_api_key; export the key."
        )
    yield
