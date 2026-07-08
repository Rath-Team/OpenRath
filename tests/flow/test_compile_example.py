"""P5.6 — example/12_compile.py runs offline (no API key) and exits cleanly."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLE = _REPO_ROOT / "example" / "12_compile.py"


def test_compile_example_runs_offline() -> None:
    assert _EXAMPLE.is_file(), f"missing example: {_EXAMPLE}"
    proc = subprocess.run(
        [sys.executable, str(_EXAMPLE)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"example failed:\n{proc.stdout}\n{proc.stderr}"
    # Exercised the manifest + validation + lifecycle sections.
    assert "Reachable provider models:" in proc.stdout
    assert "validate() problems:" in proc.stdout
    assert "Resources released on exit." in proc.stdout
