"""Adapter-level tests for ``CubeSandboxBackend`` (no live server)."""

from __future__ import annotations

import pytest

from rath.backend import (
    BackendToolCodeRun,
    BackendToolCommandRun,
    BackendToolFilesExists,
    BackendToolFilesList,
    BackendToolFilesRead,
    BackendToolFilesWrite,
    Capabilities,
    IsolationLevel,
    get,
)
from rath.backend.cubesandbox import CubeSandboxBackend


def test_registered_under_name_cubesandbox() -> None:
    inst = get("cubesandbox")
    assert isinstance(inst, CubeSandboxBackend)
    assert inst.name == "cubesandbox"


def test_capabilities_describe_microvm() -> None:
    cap = CubeSandboxBackend.capabilities()
    assert isinstance(cap, Capabilities)
    assert cap.isolation is IsolationLevel.MICROVM
    assert cap.supports_command is True
    assert cap.supports_filesystem is True
    assert cap.supports_code_interpreter is True
    assert cap.cold_start_ms_p50 == 60


def test_supported_calls_covers_all_phase1_types() -> None:
    assert CubeSandboxBackend.supported_calls() == frozenset(
        {
            BackendToolCommandRun,
            BackendToolFilesRead,
            BackendToolFilesWrite,
            BackendToolFilesList,
            BackendToolFilesExists,
            BackendToolCodeRun,
        }
    )


def test_is_available_requires_sdk_and_template(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.delitem(sys.modules, "e2b_code_interpreter", raising=False)
    monkeypatch.delenv("CUBE_TEMPLATE_ID", raising=False)
    monkeypatch.delenv("RATH_CUBESANDBOX_TEMPLATE_ID", raising=False)
    assert CubeSandboxBackend.is_available() is False
