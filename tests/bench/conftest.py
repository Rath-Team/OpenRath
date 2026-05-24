"""Bench-suite-wide gating.

``pytest-benchmark`` provides the ``benchmark`` fixture and is added to the
``dev`` dependency group. If a contributor runs the bench suite without
installing the dev extras the suite degrades to a clean skip rather than
spraying ``fixture 'benchmark' not found`` errors. The bench files import
``pytest_benchmark`` lazily so collection still works without the plugin.
"""

from __future__ import annotations

import importlib

import pytest


def _benchmark_plugin_available() -> bool:
    try:
        importlib.import_module("pytest_benchmark")
    except Exception:
        return False
    return True


collect_ignore_glob: list[str] = []
if not _benchmark_plugin_available():
    # Skip every bench_*.py file outright when the plugin is missing.
    collect_ignore_glob.append("bench_*.py")


@pytest.fixture(scope="session", autouse=True)
def _bench_plugin_required() -> None:
    """Guard fixture — second line of defence if collect_ignore_glob misses."""
    if not _benchmark_plugin_available():
        pytest.skip("pytest-benchmark not installed; run `uv sync --dev` to enable")
