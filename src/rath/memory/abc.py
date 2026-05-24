"""Memory-backend abstract base, store handle, and store spec.

Parallel to :mod:`rath.backend.abc`: :class:`MemoryStore` mirrors
:class:`~rath.backend.abc.BackendSandbox` (refcount handle),
:class:`MemoryStoreSpec` mirrors
:class:`~rath.backend.abc.BackendSandboxSpec`, and :class:`MemoryBackend`
mirrors :class:`~rath.backend.abc.Backend`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, ClassVar

from rath.memory.capabilities import MemoryCapabilities
from rath.memory.errors import MemoryStoreClosed
from rath.memory.op_types import MemoryOp
from rath.memory.results import MemoryResult

__all__ = ["MemoryStoreSpec", "MemoryStore", "MemoryBackend"]


@dataclass
class MemoryStoreSpec:
    """User-facing description of a memory store to open.

    All fields are optional; backends may ignore fields that do not apply
    (e.g. an embedded backend ignores ``account_id``/``user_id``).
    """

    namespace: str | None = None
    account_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    options: Mapping[str, Any] | None = None


@dataclass
class MemoryStore:
    """Memory store handle with reference counting.

    Lifecycle mirrors :class:`~rath.backend.abc.BackendSandbox`: each
    :class:`~rath.flow.Agent` slot, each ``with store:`` block, and any
    explicit :meth:`acquire` counts as one reference. :meth:`release`
    decrements and, when the count reaches zero, calls
    ``backend.close(self)``. There is no "force close" path -- callers that
    want immediate teardown must drop all references.

    :func:`MemoryBackend.open` returns a store with ``_refcount == 0``. The
    caller is expected to either bind it to an :class:`~rath.flow.Agent`
    (which acquires) or enter ``with store:`` (which acquires) before it can
    be safely held.
    """

    backend: "MemoryBackend"
    handle: str
    spec: MemoryStoreSpec | None = None
    closed: bool = field(default=False)
    _refcount: int = field(default=0, repr=False)

    @property
    def refcount(self) -> int:
        """Current number of live references; read-only mirror of internal state."""
        return self._refcount

    def acquire(self) -> "MemoryStore":
        """Add one reference; return ``self`` for chaining."""
        if self.closed:
            raise MemoryStoreClosed(self.handle)
        self._refcount += 1
        return self

    def release(self) -> None:
        """Drop one reference; close via the backend when the count hits zero."""
        if self.closed:
            return
        self._refcount -= 1
        if self._refcount <= 0:
            self.backend.close(self)

    def __enter__(self) -> "MemoryStore":
        return self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()

    def dispatch(self, op: MemoryOp) -> MemoryResult:
        """Apply ``op`` through :meth:`MemoryBackend.dispatch`."""
        if self.closed:
            raise MemoryStoreClosed(self.handle)
        return self.backend.dispatch(self, op)


class MemoryBackend(ABC):
    """Abstract base class for memory backends.

    Subclasses must:

    1. Set the ``name`` class attribute and register via
       :func:`rath.memory.register`.
    2. Implement the classmethods ``is_available``, ``capabilities`` and
       ``supported_ops``.
    3. Implement the instance methods ``store_count``, ``open``, ``close``
       and ``dispatch``.
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
    def capabilities(cls) -> MemoryCapabilities:
        """Return the static capability description of this backend type."""

    @classmethod
    @abstractmethod
    def supported_ops(cls) -> frozenset[type[MemoryOp]]:
        """Return :class:`MemoryOp` subclasses this backend handles."""

    @abstractmethod
    def store_count(self) -> int:
        """Return the number of open memory stores managed by this instance."""

    @abstractmethod
    def open(self, spec: MemoryStoreSpec | None = None) -> MemoryStore:
        """Open a fresh memory store and return its handle."""

    @abstractmethod
    def close(self, store: MemoryStore) -> None:
        """Close ``store`` and release resources.

        Calling close on an already-closed store is a no-op.
        """

    @abstractmethod
    def dispatch(self, store: MemoryStore, op: MemoryOp) -> MemoryResult:
        """Execute ``op`` against ``store`` and return its result.

        Implementations should raise
        :class:`~rath.memory.errors.UnsupportedMemoryOp` for op types not in
        :meth:`supported_ops`.
        """
