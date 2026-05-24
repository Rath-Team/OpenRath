"""Shared fixtures for memory-plane tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from rath.memory import registry as _memreg


@pytest.fixture
def clean_memory_registry() -> Iterator[None]:
    """Reset the memory registry around each test that touches it."""
    _memreg._reset()
    try:
        yield
    finally:
        _memreg._reset()
