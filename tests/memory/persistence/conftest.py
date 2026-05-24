"""Isolate every memory-persistence test to a tmp ``OPENRATH_HOME``."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest


@pytest.fixture(autouse=True)
def _isolate_openrath_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[Path]:
    target = tmp_path / "openrath_home"
    monkeypatch.setenv("OPENRATH_HOME", str(target))
    yield target
