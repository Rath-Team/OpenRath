"""``rath.backend.get(name)`` returns the same instance for the same name.

Per-process singleton-per-name is what makes the sandbox refcount and
backend-internal caches (e.g. ``OpenSandboxBackend._natives``) coherent
across sessions that all bind to the same backend.
"""

from __future__ import annotations

import threading

import pytest

from rath.backend import get
from rath.backend.registry import list_names


def test_get_returns_same_instance_for_same_name() -> None:
    a = get("local")
    b = get("local")
    assert a is b


def test_distinct_names_get_distinct_instances() -> None:
    if "opensandbox" not in list_names():
        pytest.skip("opensandbox backend not registered")
    local = get("local")
    other = get("opensandbox")
    assert local is not other


def test_singleton_is_thread_safe_under_first_call_race() -> None:
    from rath.backend.registry import _reset_instances

    _reset_instances()
    results: list[object] = []
    barrier = threading.Barrier(8)

    def grab() -> None:
        barrier.wait()
        results.append(get("local"))

    threads = [threading.Thread(target=grab) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    first = results[0]
    assert all(r is first for r in results)
