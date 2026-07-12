from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import rath.benchmark.task as task_module
from rath.backend import ToolExecutionFailure
from rath.benchmark import (
    BenchmarkSetupError,
    BenchmarkTask,
    CommandVerifier,
    benchmark_tasks_from_jsonl,
)
from rath.session import Session


def _task(**kwargs: Any) -> BenchmarkTask:
    return BenchmarkTask(
        task_id="task",
        name="Task",
        category="software",
        description="Fix it.",
        language="Python",
        metric="pass@1",
        verifier=CommandVerifier("true"),
        initial_files={"solution.py": "pass\n"},
        **kwargs,
    )


@pytest.mark.parametrize(
    "raw",
    [
        ToolExecutionFailure("permission_denied", "denied", "solution.py"),
        object(),
    ],
)
def test_workspace_setup_failure_is_typed_and_projected(
    raw: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(task_module, "flow_tool_files_write", lambda *args: raw)
    with pytest.raises(BenchmarkSetupError) as caught:
        _task().prepare(Session.create("empty"))
    assert caught.value.task_id == "task"
    assert caught.value.path == "solution.py"
    assert caught.value.backend_failure["ok"] is False
    assert caught.value.context["path"] == "solution.py"


def test_task_metadata_is_strictly_json_ready() -> None:
    task = _task(metadata={"path": Path("workspace"), "blob": b"abc"})
    payload = task.to_jsonable()
    assert payload["metadata"]["path"] == "workspace"
    assert payload["metadata"]["blob"]["base64"] == "YWJj"
    json.dumps(payload, allow_nan=False)
    with pytest.raises(TypeError, match="unsupported protocol"):
        _task(metadata={"bad": object()})


def test_edgebench_style_mapping_and_jsonl_loader(tmp_path: Path) -> None:
    raw = {
        "task_id": "edge-1",
        "name": "Edge Task",
        "category": "software_engineering",
        "description": "Fix the project.",
        "language": "Python",
        "metric": "pass@1",
        "internet": "false",
        "metadata": {"split": "dev"},
        "source": "unit",
    }
    task = BenchmarkTask.from_mapping(
        raw,
        verifier=CommandVerifier("true"),
        initial_files={"TASK.md": "seed"},
        max_steps=3,
    )
    assert task.metadata == {"split": "dev", "source": "unit"}
    assert task.internet is False
    path = tmp_path / "tasks.jsonl"
    path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
    loaded = benchmark_tasks_from_jsonl(
        path,
        lambda row: CommandVerifier("true"),
        initial_files_factory=lambda row: {"TASK.md": str(row["description"])},
    )
    assert loaded[0].initial_files["TASK.md"] == "Fix the project."
