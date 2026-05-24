"""Cross-backend conformance fixtures.

Each test under ``tests/memory/conformance/`` is parametrized over every
available :class:`MemoryBackend` (``"local"`` is always present; other
adapters appear only when their SDK + service is reachable). The
fixture yields a ready ``(backend, store)`` pair so test bodies stay
backend-agnostic.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from rath.memory import MemoryStore, MemoryStoreSpec
from rath.memory.abc import MemoryBackend
from rath.memory.registry import get as get_backend
from rath.memory.registry import list_names

_OV_URL = os.environ.get("OPEN_VIKING_URL", "http://127.0.0.1:1933")
_OV_CONF = Path.home() / ".openviking" / "ov.conf"


def _openviking_ready() -> bool:
    if "openviking" not in list_names():
        return False
    try:
        with urllib.request.urlopen(f"{_OV_URL}/health", timeout=1.5) as r:
            healthy = bool(json.loads(r.read().decode("utf-8")).get("healthy"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError):
        return False
    if not healthy:
        return False
    if os.environ.get("OPEN_VIKING_ROOT_API_KEY"):
        return True
    if _OV_CONF.is_file():
        try:
            return bool(
                json.loads(_OV_CONF.read_text(encoding="utf-8"))
                .get("server", {})
                .get("root_api_key")
            )
        except (OSError, json.JSONDecodeError):
            return False
    return False


def _available_backends() -> list[str]:
    out = ["local"]
    if _openviking_ready():
        out.append("openviking")
    return out


@pytest.fixture(autouse=True)
def _isolate_openrath_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[Path]:
    target = tmp_path / "openrath_home"
    monkeypatch.setenv("OPENRATH_HOME", str(target))
    yield target


@pytest.fixture(params=_available_backends())
def conformant_backend(request: pytest.FixtureRequest) -> Iterator[MemoryBackend]:
    name = request.param
    b = get_backend(name)
    yield b


def _openviking_root_api_key() -> str | None:
    env_key = os.environ.get("OPEN_VIKING_ROOT_API_KEY")
    if env_key:
        return env_key
    if _OV_CONF.is_file():
        try:
            return (
                json.loads(_OV_CONF.read_text(encoding="utf-8"))
                .get("server", {})
                .get("root_api_key")
            )
        except (OSError, json.JSONDecodeError):
            return None
    return None


@pytest.fixture
def conformant_store(
    conformant_backend: MemoryBackend,
) -> Iterator[MemoryStore]:
    options: dict = {}
    if conformant_backend.name == "openviking":
        options = {
            "url": _OV_URL,
            "api_key": _openviking_root_api_key(),
        }
    s = conformant_backend.open(MemoryStoreSpec(options=options))
    try:
        yield s
    finally:
        if not s.closed:
            conformant_backend.close(s)
