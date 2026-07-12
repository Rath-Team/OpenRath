from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rath.backend import BackendCapability
from rath.benchmark.datasets import load_edgebench

_FIXTURE = Path(__file__).parent / "fixtures" / "edgebench_task.json"
_ALL = frozenset(BackendCapability)
# What a container-based sandbox can actually offer.
_CONTAINER = frozenset(
    {BackendCapability.PER_TASK_IMAGE, BackendCapability.NETWORK_ISOLATION}
)


def _spec() -> dict[str, Any]:
    return json.loads(_FIXTURE.read_text())


def test_spec_maps_to_a_task_when_the_backend_can_host_docker() -> None:
    report = load_edgebench([_spec()], features=_ALL)
    task = report.tasks[0]
    assert task.task_id == _spec()["task_id"]
    assert task.description == _spec()["work"]["agent_query"]
    assert _spec()["work"]["image_tag"] in str(task.sandbox_spec)
    assert _spec()["judge"]["image_tag"] in task.metadata["judge_image"]


def test_the_offline_flag_is_carried_from_the_spec() -> None:
    assert _spec()["internet"] is False
    task = load_edgebench([_spec()], features=_ALL).tasks[0]
    assert task.internet is False


def test_every_task_is_skipped_on_a_container_backend() -> None:
    # Scoring runs in a second container started by the harness, which needs the
    # host Docker daemon. A container-based sandbox cannot start one, so EdgeBench
    # is unrunnable there — and says so rather than failing mid-episode.
    report = load_edgebench([_spec()], features=_CONTAINER)
    assert report.tasks == ()
    assert BackendCapability.HOST_DOCKER in report.skipped[0].missing
    assert report.coverage == 0.0


def test_coverage_is_zero_and_summarized() -> None:
    report = load_edgebench([_spec()], features=frozenset())
    assert report.coverage == 0.0
    assert "0 runnable" in report.summary()
