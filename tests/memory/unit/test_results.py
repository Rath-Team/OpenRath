"""Value-object invariants for :mod:`rath.memory.results`."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass

import pytest

from rath.memory.results import (
    MemoryCommitResult,
    MemoryEntry,
    MemoryExecutionFailure,
    MemoryFindResult,
    MemoryHit,
    MemoryListResult,
    MemoryReadResult,
    MemoryResult,
    MemoryWriteResult,
)

_RESULT_SAMPLES = [
    (MemoryHit, {"uri": "viking://user/memories/x", "score": 0.9}),
    (
        MemoryFindResult,
        {"hits": (MemoryHit(uri="viking://user/memories/x", score=0.9),)},
    ),
    (
        MemoryReadResult,
        {"uri": "viking://user/memories/x", "data": "hi", "level": "detail"},
    ),
    (MemoryEntry, {"name": "x", "uri": "viking://user/memories/x", "is_dir": False}),
    (
        MemoryListResult,
        {
            "entries": (
                MemoryEntry(name="x", uri="viking://user/memories/x", is_dir=False),
            )
        },
    ),
    (MemoryWriteResult, {"uri": "viking://user/memories/x", "bytes_written": 3}),
    (
        MemoryCommitResult,
        {"task_id": "t1", "archived_uri": None, "extracted_count": 0},
    ),
    (MemoryExecutionFailure, {"kind": "not_found", "message": "missing"}),
]


@pytest.mark.parametrize("cls,kwargs", _RESULT_SAMPLES)
def test_result_is_frozen_dataclass(cls, kwargs):
    assert is_dataclass(cls)
    obj = cls(**kwargs)
    first_field = fields(cls)[0].name
    with pytest.raises(FrozenInstanceError):
        setattr(obj, first_field, "mutated")


@pytest.mark.parametrize("cls,kwargs", _RESULT_SAMPLES)
def test_result_uses_slots(cls, kwargs):
    obj = cls(**kwargs)
    assert hasattr(cls, "__slots__")
    assert not hasattr(obj, "__dict__")


@pytest.mark.parametrize("cls,kwargs", _RESULT_SAMPLES)
def test_result_hashable_and_value_equal(cls, kwargs):
    a = cls(**kwargs)
    b = cls(**kwargs)
    assert a == b
    assert hash(a) == hash(b)


def test_memory_result_marker_is_subclassed():
    assert issubclass(MemoryFindResult, MemoryResult)
    assert issubclass(MemoryReadResult, MemoryResult)
    assert issubclass(MemoryListResult, MemoryResult)
    assert issubclass(MemoryWriteResult, MemoryResult)
    assert issubclass(MemoryCommitResult, MemoryResult)
    assert issubclass(MemoryExecutionFailure, MemoryResult)
    # MemoryHit and MemoryEntry are value parts, not standalone results.
    assert not issubclass(MemoryHit, MemoryResult)
    assert not issubclass(MemoryEntry, MemoryResult)


def test_execution_failure_kind_accepts_known_values():
    for kind in (
        "not_found",
        "unsupported",
        "transport",
        "extraction_failed",
        "store_closed",
        "unauthorized",
        "timeout",
        "invalid_uri",
        "internal",
    ):
        f = MemoryExecutionFailure(kind=kind, message="x")
        assert f.kind == kind


def test_execution_failure_kind_rejects_unknown():
    with pytest.raises(ValueError):
        MemoryExecutionFailure(kind="bogus", message="x")  # type: ignore[arg-type]


def test_memory_hit_optional_fields_default_to_none():
    hit = MemoryHit(uri="viking://u", score=0.5)
    assert hit.snippet is None
    assert hit.level is None


def test_memory_entry_size_default_none():
    e = MemoryEntry(name="x", uri="viking://u", is_dir=False)
    assert e.size is None


def test_memory_commit_result_extracted_count_minus_one_sentinel():
    r = MemoryCommitResult(task_id=None, archived_uri=None, extracted_count=-1)
    assert r.extracted_count == -1
