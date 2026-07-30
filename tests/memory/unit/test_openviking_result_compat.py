"""OpenViking SDK result-shape compatibility without a live server."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("openviking")

from rath.memory.adapters.openviking import _hits_from_findresult  # noqa: E402


def test_http_mapping_result_is_normalized() -> None:
    hits = _hits_from_findresult(
        {
            "memories": [
                {
                    "uri": "viking://user/memories/preferences/style.md",
                    "score": 0.8,
                    "abstract": "Prefers concise answers.",
                    "level": 0,
                }
            ],
            "resources": [
                {
                    "uri": "viking://resources/runbook.md",
                    "score": 0.95,
                    "overview": "Production runbook.",
                    "level": 1,
                }
            ],
            "skills": [],
        }
    )

    assert [hit.uri for hit in hits] == [
        "memory://resources/runbook.md",
        "memory://user/memories/preferences/style.md",
    ]
    assert [hit.level for hit in hits] == ["overview", "abstract"]
    assert [hit.snippet for hit in hits] == [
        "Production runbook.",
        "Prefers concise answers.",
    ]


def test_embedded_object_result_remains_supported() -> None:
    hits = _hits_from_findresult(
        SimpleNamespace(
            memories=[],
            resources=[],
            skills=[
                SimpleNamespace(
                    uri="viking://agent/skills/release",
                    score=0.7,
                    abstract="Release safely.",
                    overview=None,
                    level=2,
                )
            ],
        )
    )

    assert len(hits) == 1
    assert hits[0].uri == "memory://agent/skills/release"
    assert hits[0].level == "detail"
