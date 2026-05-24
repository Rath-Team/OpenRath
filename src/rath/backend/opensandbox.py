"""OpenSandbox backend: ``opensandbox`` SDK against ``opensandbox-server``.

Requires optional ``opensandbox`` and ``code_interpreter``, and API reachability via
environment (``OPEN_SANDBOX_DOMAIN``, ``OPEN_SANDBOX_API_KEY``, or legacy
``OPENSANDBOX_DOMAIN``) or ``~/.sandbox.toml``.

If :class:`~rath.backend.abc.BackendSandboxSpec` sets ``working_dir``,
Rath requests a host bind of that path at ``/workspace``.
The bind source must exist where the server runtime runs (e.g. Docker host),
not only where Rath runs.

The implementation is async-native: ``_aopen`` / ``_aclose`` / ``_adispatch``
run on :class:`rath._async.runtime.OpenRathRuntime`'s shared loop. The
historic ``DedicatedEventLoopThread`` indirection is gone.

Per-sandbox concurrency controls (阶段 0 of the upgrade plan):

- ``_exec_locks[handle]`` — an :class:`asyncio.Lock` serialises
  ``commands.run`` / ``code.run`` on the same sandbox (the SDK does not
  guarantee safety for overlapping interactive sessions).
- ``_fs_locks[handle][resolved_path]`` — per-path locks serialise concurrent
  writes to the same file inside one sandbox. Reads do not lock.
- Both lock dicts are created lazily inside ``_adispatch`` so the locks
  are bound to the runtime loop (总则 1). The path-keyed dict carries an
  insertion-ordered LRU of at most ``_FS_LOCK_LRU`` entries; eviction
  skips entries whose lock is currently held (总则 2).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import stat as stat_module
from collections import OrderedDict
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
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
    from opensandbox import Sandbox as _OSBSandbox
    from opensandbox.exceptions import SandboxException
    from opensandbox.models.execd import RunCommandOpts
    from opensandbox.models.filesystem import SearchEntry

    _SDK_AVAILABLE = True
except ImportError:  # pragma: no cover -- optional extra
    _SDK_AVAILABLE = False
    SandboxException = Exception  # type: ignore[assignment, misc]

try:
    from code_interpreter import CodeInterpreter

    _CI_AVAILABLE = True
except ImportError:  # pragma: no cover -- optional extra
    _CI_AVAILABLE = False

_SUPPORTED_LANGUAGES: frozenset[str] = frozenset(
    {"bash", "go", "java", "javascript", "python", "typescript"}
)

logger = logging.getLogger(__name__)

_STRICT_WORKSPACE_BIND = os.environ.get(
    "RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND", ""
).lower() in ("1", "true", "yes")


async def _await_maybe_timeout(awaitable, timeout: float | None):
    if timeout is None:
        return await awaitable
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise TimeoutError from exc


def bind_workspace_volumes_from_spec(
    spec: BackendSandboxSpec | None,
    sandbox_root: str,
) -> list[Any] | None:
    """Return a host-bind ``Volume`` for ``sandbox_root``, else ``None``.

    Creates the directory if needed (see :class:`~rath.backend.local.LocalBackend`).
    ``Host.path`` must be valid for binding on the server.
    """

    if not _SDK_AVAILABLE or spec is None or spec.working_dir is None:
        return None
    wd = Path(spec.working_dir).expanduser()
    resolved = wd.resolve(strict=False)
    resolved.mkdir(parents=True, exist_ok=True)
    if not resolved.is_dir():
        raise ValueError(
            f"BackendSandboxSpec.working_dir={spec.working_dir!r} "
            f"did not resolve to a directory ({resolved})"
        )

    from opensandbox.models.sandboxes import Host, Volume  # noqa: PLC0415

    host_str = os.fspath(resolved)
    # ``name`` must satisfy OpenSandbox DNS-label rules (e.g. lowercase, hyphens).
    return [
        Volume(
            name="rath-workspace",
            host=Host(path=host_str),
            mount_path=sandbox_root,
        )
    ]


def _message_indicates_workspace_bind_rejected(msg: str) -> bool:
    """Detect create errors that imply the host-bind / volume payload was refused."""

    t = (msg or "").lower()
    if "422" in t:
        return True
    if "not under any allowed prefix" in t:
        return True
    if "host path" in t and "allowed prefix" in t:
        return True
    return False


def _likely_workspace_bind_rejected(exc: BaseException) -> bool:
    """Best-effort classification of bind/volume-related create failures."""

    if _SDK_AVAILABLE:
        try:
            from opensandbox.exceptions import SandboxApiException

            if isinstance(exc, SandboxApiException):
                code = getattr(exc, "status_code", None)
                if code == 422:
                    return True
                return _message_indicates_workspace_bind_rejected(str(exc))
        except ImportError:  # pragma: no cover -- optional OpenSandbox SDK
            pass
    return _message_indicates_workspace_bind_rejected(str(exc))


async def _create_sandbox_with_optional_bind_fallback(
    image: str,
    timeout: timedelta,
    env: dict[str, str] | None,
    entrypoint: list[str],
    volumes: list | None,
) -> tuple[object, list | None]:
    """Create sandbox; on bind rejection, retry once with ``volumes=None``."""

    try:
        native = await _OSBSandbox.create(
            image,
            timeout=timeout,
            env=env,
            entrypoint=entrypoint,
            volumes=volumes,
        )
        return native, volumes
    except BaseException as exc:
        if (
            not volumes
            or _STRICT_WORKSPACE_BIND
            or not _likely_workspace_bind_rejected(exc)
        ):
            raise
        logger.warning(
            "OpenSandbox create rejected host bind for /workspace (%s); "
            "retrying without volumes. Allow the host path under "
            "[storage].allowed_host_paths, or set "
            "RATH_OPENSANDBOX_STRICT_WORKSPACE_BIND=1 to omit this retry.",
            exc,
            exc_info=logger.isEnabledFor(logging.DEBUG),
        )
        native = await _OSBSandbox.create(
            image,
            timeout=timeout,
            env=env,
            entrypoint=entrypoint,
            volumes=None,
        )
        return native, None


@register("opensandbox")
class OpenSandboxBackend(Backend):
    """Maps :class:`~rath.backend.tool_types.BackendTool` calls to OpenSandbox APIs.

    Commands, filesystem tools, and code runs use the sandbox SDK. Default image is
    ``opensandbox/code-interpreter``. Tool paths under :attr:`_SANDBOX_ROOT` mirror
    :attr:`BackendSandboxSpec.working_dir` when set; otherwise the workspace is empty.
    """

    name: ClassVar[str] = "opensandbox"

    _DEFAULT_IMAGE: ClassVar[str] = "opensandbox/code-interpreter:v1.0.2"
    _DEFAULT_TIMEOUT: ClassVar[timedelta] = timedelta(minutes=10)
    _DEFAULT_ENTRYPOINT: ClassVar[tuple[str, ...]] = (
        "/opt/opensandbox/code-interpreter.sh",
    )
    _SANDBOX_ROOT: ClassVar[str] = "/workspace"

    _CAPABILITIES: ClassVar[Capabilities] = Capabilities(
        isolation=IsolationLevel.CONTAINER,
        supports_command=True,
        supports_filesystem=True,
        supports_code_interpreter=True,
        cold_start_ms_p50=None,
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

    _FS_LOCK_LRU: ClassVar[int] = 64

    def __init__(self) -> None:
        self._natives: dict[str, Any] = {}
        # Locks are populated lazily inside ``_adispatch`` so they bind to
        # the runtime loop (总则 1). Empty dict construction here is safe.
        self._exec_locks: dict[str, asyncio.Lock] = {}
        self._fs_locks: dict[str, OrderedDict[str, asyncio.Lock]] = {}

    @classmethod
    def is_available(cls) -> bool:
        """Whether dependencies import and the client appears configured.

        Uses env vars or ``~/.sandbox.toml`` presence; does not ping the API.
        """
        if not (_SDK_AVAILABLE and _CI_AVAILABLE):
            return False
        if os.environ.get("OPEN_SANDBOX_DOMAIN") or os.environ.get(
            "OPENSANDBOX_DOMAIN",
        ):
            return True
        return Path.home().joinpath(".sandbox.toml").exists()

    @classmethod
    def capabilities(cls) -> Capabilities:
        return cls._CAPABILITIES

    @classmethod
    def supported_calls(cls) -> frozenset[type[BackendTool]]:
        return cls._SUPPORTED_CALLS

    def sandbox_count(self) -> int:
        return len(self._natives)

    async def _aopen(self, spec: BackendSandboxSpec | None = None) -> BackendSandbox:
        if not _SDK_AVAILABLE:  # pragma: no cover -- ``is_available()`` gate
            raise RuntimeError(
                "opensandbox SDK is not installed; "
                "install with `pip install rath[opensandbox]`"
            )
        image = spec.image if spec is not None and spec.image else self._DEFAULT_IMAGE
        timeout = (
            spec.timeout
            if spec is not None and spec.timeout is not None
            else self._DEFAULT_TIMEOUT
        )
        env = dict(spec.env) if spec is not None and spec.env is not None else None
        entrypoint = (
            list(spec.entrypoint)
            if spec is not None and spec.entrypoint is not None
            else list(self._DEFAULT_ENTRYPOINT)
        )
        return await self._open_coro(image, timeout, env, entrypoint, spec)

    def attach(
        self,
        remote_id: str,
        *,
        spec: BackendSandboxSpec | None = None,
    ) -> BackendSandbox:
        """Reattach to an already-running remote sandbox by its native id.

        Calls ``opensandbox.Sandbox.connect(remote_id)`` so the SDK pulls the
        live container metadata from the server and returns a working
        handle. The returned :class:`BackendSandbox` is indistinguishable
        from one produced by :meth:`open` — it can be used with ``dispatch``,
        ``close``, ``stream`` etc.

        ``spec`` is recorded on the :class:`BackendSandbox` purely for
        bookkeeping (e.g. session-loop replay); it is not validated against
        the live container.

        Raises whatever :func:`opensandbox.Sandbox.connect` raises when the
        remote id is missing / expired / unauthorized.
        """
        from rath._async.runtime import runtime as _runtime

        if not _SDK_AVAILABLE:  # pragma: no cover -- gated by is_available()
            raise RuntimeError(
                "opensandbox SDK is not installed; "
                "install with `pip install rath[opensandbox]`"
            )
        return _runtime().run(self._attach_coro(remote_id, spec))

    async def _attach_coro(
        self,
        remote_id: str,
        spec: BackendSandboxSpec | None,
    ) -> BackendSandbox:
        native = await _OSBSandbox.connect(remote_id)
        # The SDK populates ``native.id`` on connect; assert sanity rather
        # than trust the caller. If the SDK ever returns a different id,
        # honor what the server says.
        handle = getattr(native, "id", remote_id) or remote_id
        self._natives[handle] = native
        return BackendSandbox(backend=self, handle=handle, spec=spec)

    async def _open_coro(
        self,
        image: str,
        timeout: timedelta,
        env: dict[str, str] | None,
        entrypoint: list[str],
        spec: BackendSandboxSpec | None,
    ) -> BackendSandbox:
        volumes = bind_workspace_volumes_from_spec(spec, self._SANDBOX_ROOT)
        native, effective_volumes = await _create_sandbox_with_optional_bind_fallback(
            image,
            timeout,
            env,
            entrypoint,
            volumes,
        )
        if not effective_volumes:
            await native.commands.run(f"mkdir -p {shlex.quote(self._SANDBOX_ROOT)}")
        self._natives[native.id] = native
        return BackendSandbox(backend=self, handle=native.id, spec=spec)

    async def _aclose(self, sandbox: BackendSandbox) -> None:
        if sandbox.closed:
            return
        sandbox.closed = True
        native = self._natives.pop(sandbox.handle, None)
        # Drop per-sandbox locks. Eviction is safe even if some path-lock is
        # currently held: the holder coroutine retains its own reference to
        # the lock object, and the table only routes new lookups.
        self._exec_locks.pop(sandbox.handle, None)
        self._fs_locks.pop(sandbox.handle, None)
        if native is not None:
            await self._close_coro(native)

    async def _close_coro(self, native: Any) -> None:
        await native.kill()
        await native.close()

    def _exec_lock_for(self, handle: str) -> asyncio.Lock:
        """Get / lazy-create the per-sandbox exec lock (loop-bound, 总则 1)."""
        lock = self._exec_locks.get(handle)
        if lock is None:
            lock = asyncio.Lock()
            self._exec_locks[handle] = lock
        return lock

    def _fs_lock_for(self, handle: str, path: str) -> asyncio.Lock:
        """Get / lazy-create a per-path write lock under ``handle``.

        Implements an LRU-style bound of ``_FS_LOCK_LRU`` entries per sandbox.
        Eviction (总则 2) only drops entries whose lock is currently unlocked,
        so an active holder is never silently replaced by a fresh lock that
        would let another writer past mutual exclusion.
        """
        table = self._fs_locks.get(handle)
        if table is None:
            table = OrderedDict()
            self._fs_locks[handle] = table
        lock = table.get(path)
        if lock is None:
            lock = asyncio.Lock()
            table[path] = lock
            if len(table) > self._FS_LOCK_LRU:
                # Walk insertion order, drop the first unlocked entry. If
                # everything is locked (extreme contention), leave the table
                # oversized rather than break mutual exclusion.
                for victim_path in list(table.keys()):
                    if victim_path == path:
                        continue
                    victim = table[victim_path]
                    if not victim.locked():
                        table.pop(victim_path, None)
                        break
        else:
            # Touch for LRU ordering.
            table.move_to_end(path)
        return lock

    async def _adispatch(
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
            return await self._dispatch_coro(sandbox.handle, native, call)
        except TimeoutError as exc:
            return tool_failure_from("timeout", exc)
        except Exception as exc:
            return tool_failure_from("dispatch_error", exc)

    async def _dispatch_coro(
        self, handle: str, native: Any, call: BackendTool
    ) -> ToolResult | bool:
        match call:
            case BackendToolCommandRun():
                async with self._exec_lock_for(handle):
                    return await self._command_run(native, call)
            case BackendToolFilesRead():
                return await self._files_read(native, call)
            case BackendToolFilesWrite():
                async with self._fs_lock_for(handle, self._resolve(call.path)):
                    return await self._files_write(native, call)
            case BackendToolFilesList():
                return await self._files_list(native, call)
            case BackendToolFilesExists():
                return await self._files_exists(native, call)
            case BackendToolCodeRun():
                async with self._exec_lock_for(handle):
                    return await self._code_run(native, call)
            case _:
                return ToolExecutionFailure(
                    kind="unsupported_tool",
                    message=(
                        f"backend {self.name!r} does not support backend tool payload "
                        f"{type(call).__name__!r}"
                    ),
                    detail=type(call).__name__,
                )

    def _resolve(self, path: str) -> str:
        """Resolve ``path`` under :attr:`_SANDBOX_ROOT` unless already absolute."""
        if path.startswith("/"):
            return path
        if path in (".", "./"):
            return self._SANDBOX_ROOT
        if path.startswith("./"):
            path = path[2:]
        return f"{self._SANDBOX_ROOT}/{path}"

    async def _command_run(
        self, native: Any, call: BackendToolCommandRun
    ) -> CommandResult:
        """Run a shell command; stdin is not supported."""
        if call.stdin is not None:
            return ToolExecutionFailure(
                kind="unsupported_tool",
                message=f"backend {self.name!r} does not support stdin on commands.run",
                detail="BackendToolCommandRun",
            )
        cmd_str = call.cmd if isinstance(call.cmd, str) else _join_cmd(call.cmd)
        opts = RunCommandOpts(
            working_directory=(
                self._resolve(call.cwd) if call.cwd is not None else self._SANDBOX_ROOT
            ),
            timeout=(
                timedelta(seconds=call.timeout) if call.timeout is not None else None
            ),
            envs=dict(call.env) if call.env is not None else None,
        )
        execution = await _await_maybe_timeout(
            native.commands.run(cmd_str, opts=opts),
            call.timeout,
        )
        stdout = "".join(m.text for m in execution.logs.stdout).encode("utf-8")
        stderr = "".join(m.text for m in execution.logs.stderr).encode("utf-8")
        elapsed_ms = (
            float(execution.complete.execution_time_in_millis)
            if execution.complete is not None
            else 0.0
        )
        return CommandResult(
            exit_code=execution.exit_code if execution.exit_code is not None else 0,
            stdout=stdout,
            stderr=stderr,
            elapsed_ms=elapsed_ms,
        )

    async def _files_read(self, native: Any, call: BackendToolFilesRead) -> FileContent:
        path = self._resolve(call.path)
        try:
            if call.encoding is None:
                return FileContent(data=await native.files.read_bytes(path))
            return FileContent(
                data=await native.files.read_file(path, encoding=call.encoding)
            )
        except SandboxException as exc:
            msg = str(exc).lower()
            if "not found" in msg or "no such file" in msg or "404" in msg:
                return tool_failure_from("file_not_found", exc, detail=str(path))
            return tool_failure_from("sandbox_sdk_error", exc)

    async def _files_write(
        self, native: Any, call: BackendToolFilesWrite
    ) -> FileWriteResult:
        path = self._resolve(call.path)
        await native.files.write_file(path, call.data, mode=call.mode)
        payload = call.data.encode("utf-8") if isinstance(call.data, str) else call.data
        return FileWriteResult(bytes_written=len(payload))

    async def _files_list(self, native: Any, call: BackendToolFilesList) -> FileEntries:
        path = self._resolve(call.path)
        infos = await native.files.search(SearchEntry(path=path, pattern="*"))
        entries = [
            FileEntry(
                name=Path(info.path).name,
                path=info.path,
                is_dir=stat_module.S_ISDIR(info.mode),
            )
            for info in infos
        ]
        entries.sort(key=lambda e: e.name)
        return FileEntries(entries=tuple(entries))

    async def _files_exists(self, native: Any, call: BackendToolFilesExists) -> bool:
        path = self._resolve(call.path)
        try:
            infos = await native.files.get_file_info([path])
        except SandboxException:
            return False
        return path in infos

    async def _code_run(self, native: Any, call: BackendToolCodeRun) -> CodeResult:
        if not _CI_AVAILABLE:  # pragma: no cover -- ``is_available()`` gate
            return ToolExecutionFailure(
                kind="sdk_missing",
                message=(
                    "code-interpreter SDK is not installed; "
                    "install with `pip install rath[opensandbox]`"
                ),
            )
        if call.language not in _SUPPORTED_LANGUAGES:
            return ToolExecutionFailure(
                kind="unsupported_tool",
                message=(
                    f"backend {self.name!r} does not support language {call.language!r}"
                ),
                detail=call.language,
            )
        source = (
            _wrap_python_for_traceback(call.code)
            if call.language == "python"
            else call.code
        )
        ci = await CodeInterpreter.create(native)
        execution = await _await_maybe_timeout(
            ci.codes.run(source, language=call.language),
            call.timeout,
        )
        stdout = "".join(m.text for m in execution.logs.stdout).encode("utf-8")
        stderr = "".join(m.text for m in execution.logs.stderr).encode("utf-8")
        text = execution.result[0].text if execution.result else None
        error = _extract_execution_error(execution, stderr)
        return CodeResult(text=text, stdout=stdout, stderr=stderr, error=error)


def _join_cmd(cmd: Sequence[str]) -> str:
    """Shell-escape a argv-style command for ``commands.run``."""
    return shlex.join(cmd)


def _wrap_python_for_traceback(code: str) -> str:
    """Wrap user Python so an uncaught exception always writes a traceback to stderr.

    The OpenSandbox v1.0.2 code-interpreter image does not consistently
    populate ``Execution.error`` for top-level Python raises. We guarantee
    stderr-side surfacing by exec'ing the user source inside a try/except.
    The original ``raise`` is re-raised so the runtime still observes the
    failure (exit_code, ``Execution.error``) if it cares to. Source is
    passed as a base64 blob to avoid quoting edge cases.
    """
    import base64

    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    return (
        "import sys as _rath_sys, traceback as _rath_tb, base64 as _rath_b64\n"
        f"_rath_src = _rath_b64.b64decode({encoded!r}).decode('utf-8')\n"
        "try:\n"
        "    exec(compile(_rath_src, '<rath>', 'exec'), {'__name__': '__main__'})\n"
        "except SystemExit:\n"
        "    raise\n"
        "except BaseException:\n"
        "    _rath_tb.print_exc(file=_rath_sys.stderr)\n"
        "    raise\n"
    )


def _extract_execution_error(execution: Any, stderr: bytes) -> str | None:
    """Pick the most informative error string from an ``Execution`` result.

    Prefers ``execution.error.value`` when the runtime populated it. Falls
    back to decoded ``stderr`` (when present) and finally to a synthetic
    message from a non-zero ``execution.exit_code``. Returns ``None`` when
    no signal indicates failure.
    """
    sdk_error = execution.error.value if execution.error is not None else None
    if sdk_error:
        return sdk_error
    if stderr:
        return stderr.decode("utf-8", errors="replace")
    exit_code = getattr(execution, "exit_code", None)
    if exit_code is not None and exit_code != 0:
        return f"code execution failed with exit code {exit_code}"
    return None
