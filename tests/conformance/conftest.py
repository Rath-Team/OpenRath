"""Fixtures parametrizing ``local`` and ``opensandbox`` backends."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from rath.backend import Backend, get
from rath.backend.registry import _reset_instances
from tests.conftest import opensandbox_real

_BACKEND_PARAMS = [
    pytest.param("local", id="local"),
    pytest.param(
        "opensandbox",
        id="opensandbox",
        marks=[opensandbox_real, pytest.mark.opensandbox],
    ),
]


@pytest.fixture(params=_BACKEND_PARAMS)
def backend(request: pytest.FixtureRequest) -> Iterator[Backend]:
    """Yield a fresh backend instance for each test.

    ``rath.backend.get`` returns a per-process singleton, so we drop cached
    instances before each test to keep the conformance suite's
    ``sandbox_count() == 0`` precondition honest under shared state.
    """
    _reset_instances()
    bk = get(request.param)
    yield bk
    _reset_instances()


@pytest.fixture
def python_cmd(backend: Backend) -> list[str]:
    """``[sys.executable]`` on local; ``["python3"]`` in OpenSandbox containers."""
    import sys

    if backend.name == "local":
        return [sys.executable]
    return ["python3"]
