from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from rath.training import TrainingAdapterError, to_trl_dataset
from tests.training.test_verl_adapter import _batch_with_step


def test_importing_training_does_not_import_trl() -> None:
    code = (
        "import sys, rath.training; "
        "assert 'trl' not in sys.modules; "
        "assert 'datasets' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_missing_dependency_error_names_the_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = __import__("importlib").import_module

    def _import(name: str) -> Any:
        if name in {"datasets", "trl"}:
            raise ModuleNotFoundError(name)
        return real(name)

    monkeypatch.setattr("rath.training.adapters.trl.importlib.import_module", _import)
    with pytest.raises(TrainingAdapterError) as caught:
        to_trl_dataset(_batch_with_step())
    assert "pip install 'openrath[trl]'" in str(caught.value)


def test_rejects_a_non_batch() -> None:
    with pytest.raises(TypeError):
        to_trl_dataset({"not": "a batch"})  # type: ignore[arg-type]


def test_rows_are_episode_aligned_and_carry_atif() -> None:
    pytest.importorskip("datasets")
    dataset = to_trl_dataset(_batch_with_step())
    assert len(dataset) == 1
    row = dataset[0]
    assert row["episode_id"] == "episode"
    assert row["task_id"] == "task"
    assert row["reward"] == 1.0
    assert row["atif"]["schema_version"] == "ATIF-v1.7"
    assert row["atif"]["final_metrics"]["step_count"] == 1


def test_completion_holds_one_line_per_action() -> None:
    pytest.importorskip("datasets")
    row = to_trl_dataset(_batch_with_step())[0]
    assert "write_workspace_file" in row["completion"]
    assert len(row["completion"].splitlines()) == 1
