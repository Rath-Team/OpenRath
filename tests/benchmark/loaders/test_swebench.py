from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rath.backend import BackendCapability
from rath.benchmark.datasets import SWEBenchVerifier, load_swebench, swebench_image

_FIXTURE = Path(__file__).parent / "fixtures" / "swebench_verified_one.json"
_ALL = frozenset(BackendCapability)


def _row() -> dict[str, Any]:
    return json.loads(_FIXTURE.read_text())


def test_row_maps_to_a_task() -> None:
    report = load_swebench([_row()], features=_ALL)
    assert report.coverage == 1.0
    task = report.tasks[0]
    assert task.task_id == _row()["instance_id"]
    assert task.description == _row()["problem_statement"]
    assert task.language == "python"
    assert task.metadata["repo"] == _row()["repo"]


def test_image_name_uses_the_official_escaping() -> None:
    # Verified against Docker Hub: the double underscore becomes _1776_.
    assert (
        swebench_image("astropy__astropy-12907")
        == "swebench/sweb.eval.x86_64.astropy_1776_astropy-12907:latest"
    )


def test_task_names_its_official_image() -> None:
    task = load_swebench([_row()], features=_ALL).tasks[0]
    assert task.sandbox_spec == swebench_image(_row()["instance_id"])


def test_verifier_carries_both_test_lists() -> None:
    verifier = load_swebench([_row()], features=_ALL).tasks[0].verifier
    assert isinstance(verifier, SWEBenchVerifier)
    assert verifier.fail_to_pass == tuple(json.loads(_row()["FAIL_TO_PASS"]))
    assert verifier.pass_to_pass == tuple(json.loads(_row()["PASS_TO_PASS"]))


def test_a_backend_without_per_task_image_skips_everything() -> None:
    report = load_swebench([_row()], features=frozenset())
    assert report.tasks == ()
    assert BackendCapability.PER_TASK_IMAGE in report.skipped[0].missing
    assert report.coverage == 0.0
