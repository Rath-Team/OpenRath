"""Smoke tests: the no-key examples run offline and exit cleanly.

Only the key-free rungs are covered here (they run as real subprocesses, no
mocks). The LLM-backed examples (01, 03-05, 07, 08, 10, 11) need a live key and
would incur cost / rate limits, so they stay lint+import-checked via
`ruff check example` rather than executed. Example 09 is key-free only when no
provider is configured; with a configured key it attempts an optional live
turn, so it is intentionally excluded from the offline set.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

# (script, artifact-it-may-write-to-repo-root)
_OFFLINE_EXAMPLES = [
    ("02_session_lineage.py", "lineage_demo.jsonl"),
    ("06_mcp_tool.py", None),
    ("13_online_env.py", None),
    ("14_trajectory_collection.py", None),
    ("15_benchmark_runner.py", None),
    ("16_training_rollout_collection.py", None),
    ("17_policy_and_dag.py", None),
    ("18_benchmark_loaders.py", None),
]


@pytest.mark.parametrize("script,artifact", _OFFLINE_EXAMPLES)
def test_no_key_example_runs_offline(script: str, artifact: str | None) -> None:
    path = _REPO_ROOT / "example" / script
    assert path.is_file(), f"missing example: {path}"
    try:
        proc = subprocess.run(
            [sys.executable, str(path)],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, f"{script} failed:\n{proc.stdout}\n{proc.stderr}"
    finally:
        if artifact:
            (_REPO_ROOT / artifact).unlink(missing_ok=True)
