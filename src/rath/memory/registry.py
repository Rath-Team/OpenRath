"""Memory backend registry: register / lookup / select.

Memory backends register a class under a string name. Public lookup helpers
operate on classes; :func:`get` instantiates a backend on demand. Mirrors
:mod:`rath.backend.registry` while staying independent of it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from rath.memory.abc import MemoryBackend
from rath.memory.errors import MemoryBackendNotFound

_REGISTRY: dict[str, type[MemoryBackend]] = {}
_DEFAULT: dict[str, str] = {}

B = TypeVar("B", bound=MemoryBackend)


def register(name: str) -> Callable[[type[B]], type[B]]:
    """Decorator: register a :class:`MemoryBackend` subclass under ``name``."""

    def decorator(cls: type[B]) -> type[B]:
        if name in _REGISTRY:
            raise ValueError(f"memory backend {name!r} is already registered")
        cls.name = name
        _REGISTRY[name] = cls
        return cls

    return decorator


def list_names() -> list[str]:
    """Return the names of all registered memory backends, in registration order."""
    return list(_REGISTRY)


def get(name: str) -> MemoryBackend:
    """Look up a memory backend by name and return a fresh instance."""
    cls = _get_class(name)
    return cls()


def get_class(name: str) -> type[MemoryBackend]:
    """Look up the registered class for ``name`` without instantiating it."""
    return _get_class(name)


def is_available(name: str) -> bool:
    """Return ``True`` iff a memory backend named ``name`` is registered and available."""
    if name not in _REGISTRY:
        return False
    return _REGISTRY[name].is_available()


def preferred(names: list[str]) -> MemoryBackend:
    """Return an instance of the first available memory backend in ``names``.

    Raises :class:`MemoryBackendNotFound` if none of the listed backends are
    registered and available.
    """
    for n in names:
        if n in _REGISTRY and _REGISTRY[n].is_available():
            return _REGISTRY[n]()
    available = [n for n in _REGISTRY if _REGISTRY[n].is_available()]
    raise MemoryBackendNotFound(name=", ".join(names), available=available)


def set_default(name: str) -> None:
    """Set the default memory backend used by :func:`current`."""
    _get_class(name)  # Raises if ``name`` is unknown.
    _DEFAULT["name"] = name


def current() -> MemoryBackend:
    """Return a fresh instance of the default memory backend.

    Raises :class:`MemoryBackendNotFound` if no default has been set.
    """
    if "name" not in _DEFAULT:
        raise MemoryBackendNotFound(name="<default>", available=list_names())
    return get(_DEFAULT["name"])


def _get_class(name: str) -> type[MemoryBackend]:
    if name not in _REGISTRY:
        raise MemoryBackendNotFound(name=name, available=list_names())
    return _REGISTRY[name]


def _reset() -> None:
    """Clear the registry. Test-only helper."""
    _REGISTRY.clear()
    _DEFAULT.clear()
