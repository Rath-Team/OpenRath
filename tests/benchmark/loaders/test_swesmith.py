from __future__ import annotations

from rath.backend import BackendCapability
from rath.benchmark.datasets import SWEBenchVerifier, load_swesmith

_ALL = frozenset(BackendCapability)
_ROW = {
    "instance_id": "pallets__flask.abc123.func_basic__001",
    "repo": "pallets/flask",
    "image_name": "swesmith.x86_64.pallets_1776_flask.abc123",
    "problem_statement": "the tests fail",
    "FAIL_TO_PASS": ["tests/test_a.py::test_one"],
    "PASS_TO_PASS": ["tests/test_b.py::test_two"],
}


def test_row_maps_to_a_task_with_a_repo_level_image() -> None:
    task = load_swesmith([_ROW], features=_ALL).tasks[0]
    assert task.task_id == _ROW["instance_id"]
    # Repo-level, not instance-level: ~250 images instead of one per instance is
    # what makes a large rollout batch affordable.
    assert task.sandbox_spec == _ROW["image_name"]
    assert task.metadata["repo"] == "pallets/flask"


def test_verifier_is_the_binary_test_list_verifier() -> None:
    verifier = load_swesmith([_ROW], features=_ALL).tasks[0].verifier
    assert isinstance(verifier, SWEBenchVerifier)
    assert verifier.fail_to_pass == ("tests/test_a.py::test_one",)
    assert verifier.pass_to_pass == ("tests/test_b.py::test_two",)


def test_skipped_without_per_task_image() -> None:
    report = load_swesmith([_ROW], features=frozenset())
    assert report.coverage == 0.0
    assert BackendCapability.PER_TASK_IMAGE in report.skipped[0].missing
