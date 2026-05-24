"""Backend registry: register / lookup / select.

Backends register a class under a string name. Public lookup helpers operate
on classes; ``get(name)`` instantiates a backend on demand.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TypeVar

from rath.backend.abc import Backend
from rath.backend.errors import BackendNotFound

_REGISTRY: dict[str, type[Backend]] = {}
_DEFAULT: dict[str, str] = {}
_INSTANCES: dict[str, Backend] = {}
_INSTANCE_LOCK = threading.Lock()

B = TypeVar("B", bound=Backend)


def register(name: str) -> Callable[[type[B]], type[B]]:
    """Decorator: register a :class:`Backend` subclass under ``name``."""

    def decorator(cls: type[B]) -> type[B]:
        if name in _REGISTRY:
            raise ValueError(f"backend {name!r} is already registered")
        cls.name = name
        _REGISTRY[name] = cls
        return cls

    return decorator


def list_names() -> list[str]:
    """Return the names of all registered backends, in registration order."""
    return list(_REGISTRY)


def get(name: str) -> Backend:
    """Look up a backend by name and return the per-process singleton instance.

    The same instance is returned for repeated calls with the same ``name``,
    so per-backend caches (e.g. ``OpenSandboxBackend._natives``) and the
    sandbox refcount are coherent across all sessions in the process.
    """
    cls = _get_class(name)
    with _INSTANCE_LOCK:
        inst = _INSTANCES.get(name)
        if inst is None:
            inst = cls()
            _INSTANCES[name] = inst
    return inst


def get_class(name: str) -> type[Backend]:
    """Look up the registered class for ``name`` without instantiating it."""
    return _get_class(name)


def is_available(name: str) -> bool:
    """Return ``True`` iff a backend named ``name`` is registered and available."""
    if name not in _REGISTRY:
        return False
    return _REGISTRY[name].is_available()


def preferred(names: list[str]) -> Backend:
    """Return an instance of the first available backend in ``names``.

    Raises :class:`BackendNotFound` if none of the listed backends are
    registered and available.
    """
    for n in names:
        if n in _REGISTRY and _REGISTRY[n].is_available():
            return get(n)
    available = [n for n in _REGISTRY if _REGISTRY[n].is_available()]
    raise BackendNotFound(name=", ".join(names), available=available)


def set_default(name: str) -> None:
    """Set the default backend used by :func:`current`."""
    _get_class(name)  # Raises if ``name`` is unknown.
    _DEFAULT["name"] = name


def current() -> Backend:
    """Return a fresh instance of the default backend.

    Raises :class:`BackendNotFound` if no default has been set.
    """
    if "name" not in _DEFAULT:
        raise BackendNotFound(name="<default>", available=list_names())
    return get(_DEFAULT["name"])


def _get_class(name: str) -> type[Backend]:
    if name not in _REGISTRY:
        raise BackendNotFound(name=name, available=list_names())
    return _REGISTRY[name]


def _reset() -> None:
    """Clear the registry. Test-only helper."""
    _REGISTRY.clear()
    _DEFAULT.clear()
    with _INSTANCE_LOCK:
        _INSTANCES.clear()


def _reset_instances() -> None:
    """Drop cached backend singletons without clearing class registrations.

    Test-only helper: keeps ``LocalBackend`` / ``OpenSandboxBackend`` registered
    but forces ``get(name)`` to construct fresh instances on next call. Useful
    when a test wants an isolated backend (e.g. its own ``_open_handles`` set)
    without re-registering classes.
    """
    with _INSTANCE_LOCK:
        _INSTANCES.clear()
