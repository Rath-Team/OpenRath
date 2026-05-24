"""Error hierarchy for :mod:`rath.memory.errors`."""

from __future__ import annotations

import pickle

import pytest

from rath.memory.errors import (
    MemoryBackendError,
    MemoryBackendNotFound,
    MemoryConflict,
    MemoryNotFound,
    MemoryStoreClosed,
    UnsupportedMemoryOp,
)
from rath.memory.op_types import MemoryOp, MemoryOpFind


def test_base_is_runtime_error():
    assert issubclass(MemoryBackendError, RuntimeError)


@pytest.mark.parametrize(
    "cls",
    [
        UnsupportedMemoryOp,
        MemoryStoreClosed,
        MemoryBackendNotFound,
        MemoryNotFound,
        MemoryConflict,
    ],
)
def test_all_inherit_base(cls):
    assert issubclass(cls, MemoryBackendError)


def test_unsupported_memory_op_carries_op_type():
    exc = UnsupportedMemoryOp(MemoryOpFind, "fake")
    assert exc.op_type is MemoryOpFind
    assert exc.backend_name == "fake"
    assert "MemoryOpFind" in str(exc)
    # Round-trips through pickle (and isinstance still works).
    revived = pickle.loads(pickle.dumps(exc))
    assert isinstance(revived, UnsupportedMemoryOp)
    assert revived.op_type is MemoryOpFind
    assert revived.backend_name == "fake"


def test_memory_store_closed_carries_handle():
    exc = MemoryStoreClosed("h1")
    assert exc.handle == "h1"
    assert "h1" in str(exc)
    revived = pickle.loads(pickle.dumps(exc))
    assert revived.handle == "h1"


def test_memory_backend_not_found_lists_available():
    exc = MemoryBackendNotFound("openviking", ["fake"])
    assert exc.name == "openviking"
    assert exc.available == ["fake"]
    assert "openviking" in str(exc)
    assert "fake" in str(exc)
    revived = pickle.loads(pickle.dumps(exc))
    assert revived.name == "openviking"
    assert revived.available == ["fake"]


def test_memory_not_found_carries_uri():
    exc = MemoryNotFound("viking://x")
    assert exc.uri == "viking://x"
    assert "viking://x" in str(exc)


def test_memory_conflict_carries_uri():
    exc = MemoryConflict("viking://x")
    assert exc.uri == "viking://x"


def test_unsupported_memory_op_rejects_non_op_type():
    class NotAnOp:
        pass

    # The constructor accepts any type[MemoryOp]; static check is the only
    # guard. We assert isinstance shape rather than runtime rejection.
    exc = UnsupportedMemoryOp(MemoryOpFind, "fake")
    assert issubclass(exc.op_type, MemoryOp)
