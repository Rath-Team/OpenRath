"""Memory-plane exceptions (parallel to :mod:`rath.backend.errors`)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rath.memory.op_types import MemoryOp


__all__ = [
    "MemoryBackendError",
    "UnsupportedMemoryOp",
    "MemoryStoreClosed",
    "MemoryBackendNotFound",
    "MemoryNotFound",
    "MemoryConflict",
]


class MemoryBackendError(RuntimeError):
    """Base class for all :mod:`rath.memory` errors."""


class UnsupportedMemoryOp(MemoryBackendError):
    """Raised when a memory backend cannot service a given :class:`MemoryOp` type."""

    def __init__(self, op_type: type["MemoryOp"], backend_name: str) -> None:
        self.op_type = op_type
        self.backend_name = backend_name
        super().__init__(
            f"memory backend {backend_name!r} does not support op {op_type.__name__!r}"
        )

    def __reduce__(self) -> tuple[type, tuple[type, str]]:
        return (self.__class__, (self.op_type, self.backend_name))


class MemoryStoreClosed(MemoryBackendError):
    """Raised when an op is dispatched against an already-closed :class:`MemoryStore`."""

    def __init__(self, handle: str) -> None:
        self.handle = handle
        super().__init__(f"memory store {handle!r} is already closed")

    def __reduce__(self) -> tuple[type, tuple[str]]:
        return (self.__class__, (self.handle,))


class MemoryBackendNotFound(MemoryBackendError):
    """Raised when a memory backend is requested by name but isn't registered."""

    def __init__(self, name: str, available: list[str]) -> None:
        self.name = name
        self.available = available
        super().__init__(
            f"memory backend {name!r} is not registered; "
            f"available backends: {available!r}"
        )

    def __reduce__(self) -> tuple[type, tuple[str, list[str]]]:
        return (self.__class__, (self.name, self.available))


class MemoryNotFound(MemoryBackendError):
    """Raised when an explicit URI is read but the backend has no such entry."""

    def __init__(self, uri: str) -> None:
        self.uri = uri
        super().__init__(f"memory uri {uri!r} not found")

    def __reduce__(self) -> tuple[type, tuple[str]]:
        return (self.__class__, (self.uri,))


class MemoryConflict(MemoryBackendError):
    """Raised when a write collides with an existing entry under conflicting rules."""

    def __init__(self, uri: str) -> None:
        self.uri = uri
        super().__init__(f"memory uri {uri!r} write conflict")

    def __reduce__(self) -> tuple[type, tuple[str]]:
        return (self.__class__, (self.uri,))
