"""CubeSandbox backend: E2B-compatible REST via ``e2b-code-interpreter`` SDK.

Drives TencentCloud CubeSandbox (https://github.com/TencentCloud/CubeSandbox)
through its E2B-compatible API on port 3000. Requires the optional
``e2b-code-interpreter`` SDK and a pre-created Cube template id surfaced via
``CUBE_TEMPLATE_ID``.
"""

from __future__ import annotations

import logging
import os
import shlex
from typing import Any, ClassVar

from rath.backend.abc import Backend, BackendSandbox, BackendSandboxSpec
from rath.backend.capabilities import Capabilities, IsolationLevel
from rath.backend.registry import register
from rath.backend.results import (
    CodeResult,
    CommandResult,
    FileContent,
    FileEntries,
    FileEntry,
    FileWriteResult,
    ToolExecutionFailure,
    ToolResult,
    tool_failure_from,
)
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
        if not _SDK_AVAILABLE:  # pragma: no cover -- ``is_available()`` gate
            raise RuntimeError(
                "e2b-code-interpreter SDK is not installed; "
                "install with `pip install openrath[cubesandbox]`"
            )
        template = (
            spec.image
            if spec is not None and spec.image
            else _template_id_from_env()
        )
        if template is None:
            raise RuntimeError(
                "CubeSandbox template id is missing; set CUBE_TEMPLATE_ID or "
                "RATH_CUBESANDBOX_TEMPLATE_ID, or pass BackendSandboxSpec(image=...)"
            )
        timeout_s = (
            spec.timeout.total_seconds()
            if spec is not None and spec.timeout is not None
            else self._DEFAULT_TIMEOUT_S
        )
        envs = dict(spec.env) if spec is not None and spec.env is not None else None
        if spec is not None and spec.entrypoint:
            logger.warning(
                "CubeSandbox templates own their entrypoint; "
                "BackendSandboxSpec.entrypoint=%r is ignored",
                list(spec.entrypoint),
            )
        native = _E2BSandbox.create(
            template=template, timeout=timeout_s, envs=envs
        )
        # Best-effort workspace mkdir; ignore failures (e.g. template already
        # provides /home/user/workspace).
        try:
            native.commands.run(f"mkdir -p {self._SANDBOX_ROOT}")
        except Exception:  # pragma: no cover -- template-dependent
            logger.debug("workspace mkdir failed (probably already present)")
        self._natives[native.sandbox_id] = native
        return BackendSandbox(backend=self, handle=native.sandbox_id, spec=spec)

    def attach(
        self,
        remote_id: str,
        *,
        spec: BackendSandboxSpec | None = None,
    ) -> BackendSandbox:
        """Re-attach to an already-running Cube sandbox by its remote id."""
        if not _SDK_AVAILABLE:  # pragma: no cover -- ``is_available()`` gate
            raise RuntimeError(
                "e2b-code-interpreter SDK is not installed; "
                "install with `pip install openrath[cubesandbox]`"
            )
        native = _E2BSandbox.connect(remote_id)
        handle = getattr(native, "sandbox_id", remote_id) or remote_id
        self._natives[handle] = native
        return BackendSandbox(backend=self, handle=handle, spec=spec)

    def close(self, sandbox: BackendSandbox) -> None:
        if sandbox.closed:
            return
        sandbox.closed = True
        native = self._natives.pop(sandbox.handle, None)
        if native is not None:
            native.kill()

    def dispatch(
        self, sandbox: BackendSandbox, call: BackendTool
    ) -> ToolResult | bool:
        if sandbox.closed:
            return ToolExecutionFailure(
                kind="sandbox_closed",
                message=f"backend sandbox {sandbox.handle!r} is already closed",
            )
        native = self._natives.get(sandbox.handle)
        if native is None:
            return ToolExecutionFailure(
                kind="sandbox_closed",
                message="native sandbox handle is missing; cannot dispatch",
            )
        try:
            match call:
                case BackendToolCommandRun():
                    return self._command_run(native, call)
                case BackendToolFilesRead():
                    return self._files_read(native, call)
                case BackendToolFilesWrite():
                    return self._files_write(native, call)
                case BackendToolFilesList():
                    return self._files_list(native, call)
                case BackendToolFilesExists():
                    return self._files_exists(native, call)
                case BackendToolCodeRun():
                    return self._code_run(native, call)
                case _:
                    return ToolExecutionFailure(
                        kind="unsupported_tool",
                        message=(
                            f"backend {self.name!r} does not support payload "
                            f"{type(call).__name__!r}"
                        ),
                        detail=type(call).__name__,
                    )
        except TimeoutError as exc:
            return tool_failure_from("timeout", exc)
        except Exception as exc:  # pragma: no cover -- defensive
            return tool_failure_from("dispatch_error", exc)

    def _resolve(self, path: str) -> str:
        """Resolve ``path`` under ``_SANDBOX_ROOT`` unless already absolute."""
        if path.startswith("/"):
            return path
        if path in (".", "./"):
            return self._SANDBOX_ROOT
        if path.startswith("./"):
            path = path[2:]
        return f"{self._SANDBOX_ROOT}/{path}"

    def _command_run(
        self, native: Any, call: BackendToolCommandRun
    ) -> ToolResult:
        if call.stdin is not None:
            return ToolExecutionFailure(
                kind="unsupported_tool",
                message=(
                    f"backend {self.name!r} does not support stdin on commands.run"
                ),
                detail="BackendToolCommandRun",
            )
        cmd_str = call.cmd if isinstance(call.cmd, str) else shlex.join(call.cmd)
        cwd = self._resolve(call.cwd) if call.cwd is not None else self._SANDBOX_ROOT
        envs = dict(call.env) if call.env is not None else None
        result = native.commands.run(
            cmd_str, cwd=cwd, envs=envs, timeout=call.timeout
        )
        stdout = (
            result.stdout.encode("utf-8")
            if isinstance(result.stdout, str)
            else result.stdout or b""
        )
        stderr = (
            result.stderr.encode("utf-8")
            if isinstance(result.stderr, str)
            else result.stderr or b""
        )
        return CommandResult(
            exit_code=int(result.exit_code or 0),
            stdout=stdout,
            stderr=stderr,
            elapsed_ms=0.0,
        )

    def _files_read(
        self, native: Any, call: BackendToolFilesRead
    ) -> ToolResult:
        path = self._resolve(call.path)
        try:
            data = native.files.read(path)
        except FileNotFoundError as exc:
            return tool_failure_from("file_not_found", exc, detail=path)
        except Exception as exc:
            msg = str(exc).lower()
            if "not found" in msg or "404" in msg:
                return tool_failure_from("file_not_found", exc, detail=path)
            return tool_failure_from("sandbox_sdk_error", exc)
        # Normalize to what ``BackendToolFilesRead.encoding`` asked for. The
        # E2B SDK's ``files.read`` returns ``str`` by default; only convert
        # when the caller's intent (encoding=None ⇒ bytes) disagrees.
        if call.encoding is None and isinstance(data, str):
            return FileContent(data=data.encode("utf-8"))
        if call.encoding is not None and isinstance(data, bytes):
            return FileContent(data=data.decode(call.encoding))
        return FileContent(data=data)

    def _files_write(
        self, native: Any, call: BackendToolFilesWrite
    ) -> FileWriteResult:
        path = self._resolve(call.path)
        native.files.write(path, call.data)
        payload = (
            call.data.encode("utf-8") if isinstance(call.data, str) else call.data
        )
        return FileWriteResult(bytes_written=len(payload))

    def _files_list(
        self, native: Any, call: BackendToolFilesList
    ) -> FileEntries:
        path = self._resolve(call.path)
        raw = native.files.list(path)
        entries = [
            FileEntry(
                name=item.name,
                path=getattr(item, "path", f"{path.rstrip('/')}/{item.name}"),
                is_dir=getattr(item, "type", "file") == "dir",
            )
            for item in raw
        ]
        entries.sort(key=lambda e: e.name)
        return FileEntries(entries=tuple(entries))

    def _files_exists(
        self, native: Any, call: BackendToolFilesExists
    ) -> bool:
        path = self._resolve(call.path)
        return bool(native.files.exists(path))

    def _code_run(self, native: Any, call: BackendToolCodeRun) -> ToolResult:
        raise NotImplementedError("Task 4")
