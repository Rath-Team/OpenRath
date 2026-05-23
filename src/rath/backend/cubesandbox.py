"""CubeSandbox backend: E2B-compatible REST via ``e2b-code-interpreter`` SDK.

Drives TencentCloud CubeSandbox (https://github.com/TencentCloud/CubeSandbox)
through its E2B-compatible API on port 3000. Requires the optional
``e2b-code-interpreter`` SDK and a pre-created Cube template id surfaced via
``CUBE_TEMPLATE_ID``.
"""

from __future__ import annotations

import logging
import os
from typing import Any, ClassVar

from rath.backend.abc import Backend, BackendSandbox, BackendSandboxSpec
from rath.backend.capabilities import Capabilities, IsolationLevel
from rath.backend.registry import register
from rath.backend.results import ToolResult
from rath.backend.tool_types import (
    BackendTool,
    BackendToolCodeRun,
    BackendToolCommandRun,
    BackendToolFilesExists,
    BackendToolFilesList,
    BackendToolFilesRead,
    BackendToolFilesWrite,
)

try:
    from e2b_code_interpreter import Sandbox as _E2BSandbox

    _SDK_AVAILABLE = True
except ImportError:  # pragma: no cover -- optional extra
    _SDK_AVAILABLE = False
    _E2BSandbox = None  # type: ignore[assignment, misc]

logger = logging.getLogger(__name__)

_SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"python"})


def _template_id_from_env() -> str | None:
    """Return the configured Cube template id; ``CUBE_TEMPLATE_ID`` wins.

    Falls back to the Rath-namespaced ``RATH_CUBESANDBOX_TEMPLATE_ID`` so users
    who run more than one E2B-compatible backend can keep them isolated.
    """
    cube = os.environ.get("CUBE_TEMPLATE_ID")
    if cube:
        return cube
    return os.environ.get("RATH_CUBESANDBOX_TEMPLATE_ID")


@register("cubesandbox")
class CubeSandboxBackend(Backend):
    """Maps :class:`BackendTool` calls into a CubeSandbox micro-VM via E2B."""

    name: ClassVar[str] = "cubesandbox"

    _SANDBOX_ROOT: ClassVar[str] = "/home/user/workspace"
    _DEFAULT_TIMEOUT_S: ClassVar[float] = 600.0

    _CAPABILITIES: ClassVar[Capabilities] = Capabilities(
        isolation=IsolationLevel.MICROVM,
        supports_command=True,
        supports_filesystem=True,
        supports_code_interpreter=True,
        cold_start_ms_p50=60,
        max_sandboxes=None,
    )

    _SUPPORTED_CALLS: ClassVar[frozenset[type[BackendTool]]] = frozenset(
        {
            BackendToolCommandRun,
            BackendToolFilesRead,
            BackendToolFilesWrite,
            BackendToolFilesList,
            BackendToolFilesExists,
            BackendToolCodeRun,
        }
    )

    def __init__(self) -> None:
        self._natives: dict[str, Any] = {}

    @classmethod
    def is_available(cls) -> bool:
        """Whether the SDK is importable and a template id is configured.

        Cheap: no network. ``CUBE_TEMPLATE_ID`` (or the Rath alias) being set
        is the strongest local signal that a Cube deployment is in use.
        """
        if not _SDK_AVAILABLE:
            return False
        return _template_id_from_env() is not None

    @classmethod
    def capabilities(cls) -> Capabilities:
        return cls._CAPABILITIES

    @classmethod
    def supported_calls(cls) -> frozenset[type[BackendTool]]:
        return cls._SUPPORTED_CALLS

    def sandbox_count(self) -> int:
        return len(self._natives)

    def open(self, spec: BackendSandboxSpec | None = None) -> BackendSandbox:
        raise NotImplementedError("Task 2")

    def close(self, sandbox: BackendSandbox) -> None:
        raise NotImplementedError("Task 2")

    def dispatch(
        self, sandbox: BackendSandbox, call: BackendTool
    ) -> ToolResult | bool:
        raise NotImplementedError("Task 3")
