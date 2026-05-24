"""Backend abstract base, sandbox handle, and sandbox spec.

Backends expose a *synchronous* public API (``open`` / ``close`` /
``dispatch``) and an internal *asynchronous* protocol
(``_aopen`` / ``_aclose`` / ``_adispatch``). The sync methods funnel into
the internal coroutines via :class:`rath._async.runtime.OpenRathRuntime`,
which is the single background event loop OpenRath shares across all
subsystems.

Subclasses MUST implement the async hooks. The sync defaults provided here
schedule each call on the runtime; this gives any backend true cross-call
concurrency for free as long as its async implementation is non-blocking.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from types import TracebackType
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from rath.backend.stream import Stream

from rath.backend.capabilities import Capabilities
from rath.backend.errors import BackendSandboxClosed
from rath.backend.results import ToolResult
from rath.backend.tool_types import BackendTool


@dataclass
class BackendSandboxSpec:
    """User-facing description of a sandbox to open.

    Fields are intentionally optional. Each backend may ignore fields that do
    not apply (e.g. ``LocalBackend`` ignores ``image``).
    """

    image: str | None = None
    entrypoint: Sequence[str] | None = None
    env: Mapping[str, str] | None = None
    timeout: timedelta | None = None
    working_dir: str | None = None


@dataclass
class BackendSandbox:
    """Sandbox handle with reference counting.

    Lifecycle is governed by :attr:`_refcount`: each :class:`Session.sandbox`
    slot, each ``with sandbox:`` block, and any explicit :meth:`acquire` counts
    as one reference. :meth:`release` decrements and, when the count reaches
    zero, calls ``backend.close(self)``. There is no "force close" path —
    callers that want immediate teardown must drop all references.

    :func:`Backend.open` returns a sandbox with ``_refcount == 0``. The caller
    is expected to either bind it to a :class:`Session` (which acquires) or
    enter ``with sandbox:`` (which acquires) before it can be safely held.
    """

    backend: "Backend"
    handle: str
    spec: BackendSandboxSpec | None = None
    closed: bool = field(default=False)
    _refcount: int = field(default=0, repr=False)
    # ``_refcount`` is read/written from both the host thread (sync facade)
    # and the runtime loop thread (async session loop). Per 阶段 0 总则 5
    # the field is guarded by a per-instance lock.
    _refcount_lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False, compare=False
    )

    @property
    def refcount(self) -> int:
        """Current number of live references; read-only mirror of internal state."""
        with self._refcount_lock:
            return self._refcount

    def acquire(self) -> "BackendSandbox":
        """Add one reference; return ``self`` for chaining."""
        with self._refcount_lock:
            if self.closed:
                raise BackendSandboxClosed(self.handle)
            self._refcount += 1
        return self

    def release(self) -> None:
        """Drop one reference; close via the backend when the count hits zero."""
        with self._refcount_lock:
            if self.closed:
                return
            self._refcount -= 1
            should_close = self._refcount <= 0
        if should_close:
            self.backend.close(self)

    def __enter__(self) -> "BackendSandbox":
        return self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()

    def dispatch(self, call: BackendTool) -> ToolResult | bool:
        """Apply ``call`` through :meth:`~rath.backend.abc.Backend.dispatch`."""
        if self.closed:
            raise BackendSandboxClosed(self.handle)
        return self.backend.dispatch(self, call)

    def stream(self, *, buffer: int = 0) -> "Stream":
        """Return a fresh :class:`Stream` bound to this sandbox.

        ``buffer=0`` (the default) means an unbounded queue; set a positive integer
        to apply backpressure on :meth:`Stream.submit`.
        """
        from rath.backend.stream import Stream as _Stream

        return _Stream(self, buffer=buffer)


class Backend(ABC):
    """Abstract base class for sandbox backends.

    Subclasses must:

    1. Set the ``name`` class attribute and register via
       :func:`rath.backend.register`.
    2. Implement the static ``is_available``, ``capabilities`` and
       ``supported_calls`` classmethods.
    3. Implement the instance method ``sandbox_count``.
    4. Implement the async hooks ``_aopen``, ``_aclose`` and ``_adispatch``.
       The sync ``open`` / ``close`` / ``dispatch`` defaults below route
       these through :class:`rath._async.runtime.OpenRathRuntime` so a
       single background loop services every subsystem concurrently.
    """

    name: ClassVar[str]

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        """Return whether this backend is usable in the current environment.

        Must be cheap (microseconds, no network, no subprocess). Examples:
        check that a required SDK is importable, or that a config file or
        environment variable is present.
        """

    @classmethod
    @abstractmethod
    def capabilities(cls) -> Capabilities:
        """Return the static capability description of this backend type."""

    @classmethod
    @abstractmethod
    def supported_calls(cls) -> frozenset[type[BackendTool]]:
        """Return :class:`~rath.backend.tool_types.BackendTool` subclasses this backend handles."""

    @abstractmethod
    def sandbox_count(self) -> int:
        """Return the number of open sandboxes managed by this instance."""

    # ----- internal async hooks (subclasses MUST implement) ----------------

    @abstractmethod
    async def _aopen(self, spec: BackendSandboxSpec | None = None) -> BackendSandbox:
        """Open a fresh sandbox; the async implementation."""

    @abstractmethod
    async def _aclose(self, sandbox: BackendSandbox) -> None:
        """Close ``sandbox`` and release resources; idempotent."""

    @abstractmethod
    async def _adispatch(
        self, sandbox: BackendSandbox, call: BackendTool
    ) -> ToolResult | bool:
        """Execute ``call`` against ``sandbox``; the async implementation."""

    # ----- public sync facade (default routes through the runtime) ---------

    def open(self, spec: BackendSandboxSpec | None = None) -> BackendSandbox:
        """Open a fresh sandbox and return its handle (sync facade)."""
        from rath._async.runtime import runtime as _runtime

        return _runtime().run(self._aopen(spec))

    def close(self, sandbox: BackendSandbox) -> None:
        """Close ``sandbox`` and release resources (sync facade).

        Calling close on an already-closed sandbox is a no-op.
        """
        from rath._async.runtime import runtime as _runtime

        _runtime().run(self._aclose(sandbox))

    def dispatch(self, sandbox: BackendSandbox, call: BackendTool) -> ToolResult | bool:
        """Execute ``call`` against ``sandbox`` and return its result (sync facade)."""
        from rath._async.runtime import runtime as _runtime

        return _runtime().run(self._adispatch(sandbox, call))
