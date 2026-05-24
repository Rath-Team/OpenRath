"""Host-process backend: subprocesses and filesystem under a temp working directory.

Always available. Relative paths in tool calls are resolved against the sandbox
working directory; absolute paths pass through unchanged.

The implementation is async-internal: ``_aopen`` / ``_aclose`` / ``_adispatch``
are the canonical entry points. Each blocking primitive (``subprocess.run``,
``Path.write_bytes`` …) is offloaded to a thread pool via
:func:`asyncio.to_thread`, so multiple ``dispatch`` calls funnelled through
:class:`rath._async.runtime.OpenRathRuntime` run truly in parallel even though
the underlying syscalls are synchronous.

Per 阶段 0 of the upgrade plan:

- The handle sets ``_open_handles`` / ``_owned_handles`` are mutated only from
  the runtime loop thread (总则 9). Read access from the host thread reads
  ``sandbox_count()`` only, which is a single ``len()`` and is GIL-atomic.
- No ``asyncio.Lock`` is needed here because every ``_adispatch`` invocation
  for the same sandbox runs an isolated worker thread per call; there is no
  shared in-process mutable state between calls beyond the working dir, and
  filesystem race semantics match the host OS's normal semantics — same as
  the previous sync implementation.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, ClassVar

from rath.backend.abc import Backend, BackendSandbox, BackendSandboxSpec
from rath.backend.capabilities import Capabilities, IsolationLevel
from rath.backend.errors import UnsupportedBackendTool
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
from rath.utils.decoding import decode_subprocess_output


@register("local")
class LocalBackend(Backend):
    """Run tool calls as host-side subprocesses with a per-sandbox working dir."""

    name: ClassVar[str] = "local"

    _CAPABILITIES: ClassVar[Capabilities] = Capabilities(
        isolation=IsolationLevel.PROCESS,
        supports_command=True,
        supports_filesystem=True,
        supports_code_interpreter=True,
        cold_start_ms_p50=10,
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
        self._open_handles: set[str] = set()
        self._owned_handles: set[str] = set()

    @classmethod
    def is_available(cls) -> bool:
        return True

    @classmethod
    def capabilities(cls) -> Capabilities:
        return cls._CAPABILITIES

    @classmethod
    def supported_calls(cls) -> frozenset[type[BackendTool]]:
        return cls._SUPPORTED_CALLS

    def sandbox_count(self) -> int:
        return len(self._open_handles)

    async def _aopen(self, spec: BackendSandboxSpec | None = None) -> BackendSandbox:
        if spec is None or spec.working_dir is None:
            owns_working_dir = True
            working_dir = await asyncio.to_thread(
                tempfile.mkdtemp, prefix="rath-local-"
            )
        else:
            owns_working_dir = False
            working_dir = spec.working_dir
        await asyncio.to_thread(
            lambda: Path(working_dir).mkdir(parents=True, exist_ok=True)
        )
        sandbox = BackendSandbox(backend=self, handle=working_dir, spec=spec)
        # Mutate the handle sets from the runtime loop thread only (总则 9).
        self._open_handles.add(working_dir)
        if owns_working_dir:
            self._owned_handles.add(working_dir)
        return sandbox

    async def _aclose(self, sandbox: BackendSandbox) -> None:
        if sandbox.closed:
            return
        # See total set membership before marking closed so concurrent
        # ``_aclose`` invocations on the same handle are idempotent: only
        # the first will see ``owns_working_dir == True``.
        self._open_handles.discard(sandbox.handle)
        owns_working_dir = sandbox.handle in self._owned_handles
        self._owned_handles.discard(sandbox.handle)
        sandbox.closed = True
        if owns_working_dir:
            await asyncio.to_thread(shutil.rmtree, sandbox.handle, ignore_errors=True)

    async def _adispatch(
        self, sandbox: BackendSandbox, call: BackendTool
    ) -> ToolResult | bool:
        if sandbox.closed:
            return ToolExecutionFailure(
                kind="sandbox_closed",
                message=f"backend sandbox {sandbox.handle!r} is already closed",
            )
        match call:
            case BackendToolCommandRun():
                return await asyncio.to_thread(self._command_run, sandbox, call)
            case BackendToolFilesRead():
                return await asyncio.to_thread(self._files_read, sandbox, call)
            case BackendToolFilesWrite():
                return await asyncio.to_thread(self._files_write, sandbox, call)
            case BackendToolFilesList():
                return await asyncio.to_thread(self._files_list, sandbox, call)
            case BackendToolFilesExists():
                return await asyncio.to_thread(self._files_exists, sandbox, call)
            case BackendToolCodeRun():
                return await asyncio.to_thread(self._code_run, sandbox, call)
            case _:
                exc = UnsupportedBackendTool(type(call), self.name)
                return tool_failure_from(
                    "unsupported_tool", exc, detail=type(call).__name__
                )

    def _resolve(self, sandbox: BackendSandbox, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return Path(sandbox.handle) / path

    def _command_run(
        self, sandbox: BackendSandbox, call: BackendToolCommandRun
    ) -> CommandResult | ToolExecutionFailure:
        cwd = self._resolve(sandbox, call.cwd) if call.cwd else Path(sandbox.handle)
        env_arg: dict[str, str] | None = None
        if call.env is not None:
            env_arg = {**os.environ, **call.env}
        start = time.perf_counter()
        if isinstance(call.cmd, str):
            if sys.platform == "win32":
                popen_args: list[str] | str = call.cmd
                use_shell = True
            else:
                popen_args = ["/bin/sh", "-c", call.cmd]
                use_shell = False
        else:
            popen_args = list(call.cmd)
            use_shell = False

        run_kw: dict[str, Any] = dict(
            args=popen_args,
            shell=use_shell,
            input=call.stdin,
            cwd=str(cwd),
            env=env_arg,
            capture_output=True,
        )
        if call.timeout is not None:
            run_kw["timeout"] = call.timeout
        try:
            proc = subprocess.run(**run_kw)
        except subprocess.TimeoutExpired as exc:
            return tool_failure_from("timeout", exc)
        except (FileNotFoundError, OSError) as exc:
            return tool_failure_from("os_error", exc)
        except Exception as exc:
            return tool_failure_from("unexpected", exc)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return CommandResult(
            exit_code=int(proc.returncode),
            stdout=proc.stdout if proc.stdout is not None else b"",
            stderr=proc.stderr if proc.stderr is not None else b"",
            elapsed_ms=elapsed_ms,
        )

    def _files_read(
        self, sandbox: BackendSandbox, call: BackendToolFilesRead
    ) -> FileContent | ToolExecutionFailure:
        p = self._resolve(sandbox, call.path)
        try:
            if call.encoding is None:
                return FileContent(data=p.read_bytes())
            return FileContent(data=p.read_text(encoding=call.encoding))
        except FileNotFoundError as exc:
            return tool_failure_from("file_not_found", exc, detail=str(p))
        except OSError as exc:
            return tool_failure_from("os_error", exc)

    def _files_write(
        self, sandbox: BackendSandbox, call: BackendToolFilesWrite
    ) -> FileWriteResult | ToolExecutionFailure:
        p = self._resolve(sandbox, call.path)
        payload_bytes = (
            call.data.encode("utf-8") if isinstance(call.data, str) else call.data
        )
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(payload_bytes)
        except OSError as exc:
            return tool_failure_from("os_error", exc)
        with contextlib.suppress(OSError):
            p.chmod(call.mode)
        return FileWriteResult(bytes_written=len(payload_bytes))

    def _files_list(
        self, sandbox: BackendSandbox, call: BackendToolFilesList
    ) -> FileEntries | ToolExecutionFailure:
        p = self._resolve(sandbox, call.path)
        try:
            entries = [
                FileEntry(
                    name=child.name,
                    path=str(child),
                    is_dir=child.is_dir(),
                )
                for child in p.iterdir()
            ]
        except OSError as exc:
            return tool_failure_from("os_error", exc)
        entries.sort(key=lambda e: e.name)
        return FileEntries(entries=tuple(entries))

    def _files_exists(
        self, sandbox: BackendSandbox, call: BackendToolFilesExists
    ) -> bool:
        try:
            return self._resolve(sandbox, call.path).exists()
        except OSError:
            # Treat permission errors / unreadable parent dirs as "not present"
            # rather than raising into the loop; matches POSIX stat() semantics
            # from the caller's perspective.
            return False

    def _code_run(
        self, sandbox: BackendSandbox, call: BackendToolCodeRun
    ) -> CodeResult | ToolExecutionFailure:
        if call.language != "python":
            exc = UnsupportedBackendTool(type(call), self.name)
            return tool_failure_from("unsupported_tool", exc, detail=call.language)
        work = Path(sandbox.handle)
        tmp = work / f".rath_code_{uuid.uuid4().hex}.py"
        tmp.write_text(call.code, encoding="utf-8")
        proc: subprocess.CompletedProcess[bytes] | None = None
        try:
            run_kw: dict[str, Any] = dict(
                args=[sys.executable, str(tmp)],
                cwd=str(work),
                capture_output=True,
            )
            if call.timeout is not None:
                run_kw["timeout"] = call.timeout
            proc = subprocess.run(**run_kw)
        except subprocess.TimeoutExpired as exc:
            return tool_failure_from("timeout", exc)
        except (FileNotFoundError, OSError) as exc:
            return tool_failure_from("os_error", exc)
        finally:
            with contextlib.suppress(FileNotFoundError, OSError):
                tmp.unlink()
        assert proc is not None
        error = decode_subprocess_output(proc.stderr) if proc.returncode != 0 else None
        return CodeResult(
            text=None,
            stdout=proc.stdout if proc.stdout is not None else b"",
            stderr=proc.stderr if proc.stderr is not None else b"",
            error=error,
        )
