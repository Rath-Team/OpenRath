"""The base install must default to the local backend.

v1.2.0 ships a zero-dependency local memory backend; ``rath.memory`` pins
it as the default at import time so ``rath.memory.current()`` works out
of the box.
"""

from __future__ import annotations

import rath.memory as rm
from rath.memory.adapters.local import LocalMemoryBackend


def test_default_backend_is_local() -> None:
    backend = rm.current()
    assert isinstance(backend, LocalMemoryBackend)
    # The class is registered under the canonical name "local".
    assert backend.name == "local"


def test_local_appears_in_list_names() -> None:
    assert "local" in rm.list_names()


def test_local_is_available_without_extras() -> None:
    assert rm.is_available("local") is True
