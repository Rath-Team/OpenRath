"""Value-object invariants for :mod:`rath.memory.op_types`.

Each concrete ``MemoryOp`` subclass must be:

* a frozen dataclass (mutation raises ``FrozenInstanceError``),
* slotted (``__slots__`` defined; no ``__dict__``),
* hashable and value-equal,
* a subclass of the ``MemoryOp`` marker.
"""

from __future__ import annotations

import typing
from dataclasses import FrozenInstanceError, fields, is_dataclass
from typing import get_args

import pytest

from rath.memory.op_types import (
    MemoryOp,
    MemoryOpCommit,
    MemoryOpFind,
    MemoryOpList,
    MemoryOpRead,
    MemoryOpResource,
    MemoryOpSearch,
    MemoryOpTree,
    MemoryOpWrite,
)

_OP_SAMPLES = [
    (MemoryOpWrite, {"uri": "viking://user/memories/x", "content": "hi"}),
    (MemoryOpRead, {"uri": "viking://user/memories/x"}),
    (MemoryOpList, {"uri": "viking://user/memories/"}),
    (MemoryOpTree, {"uri": "viking://user/memories/"}),
    (MemoryOpFind, {"query": "dark mode"}),
    (
        MemoryOpSearch,
        {"query": "login flow", "session_id": "s1"},
    ),
    (MemoryOpResource, {"source": "https://example.com/doc"}),
    (
        MemoryOpCommit,
        {"session_id": "s1", "messages": (("role", "user"),)},
    ),
]


@pytest.mark.parametrize("cls,kwargs", _OP_SAMPLES)
def test_op_is_marker_subclass(cls, kwargs):
    op = cls(**kwargs)
    assert isinstance(op, MemoryOp)


@pytest.mark.parametrize("cls,kwargs", _OP_SAMPLES)
def test_op_is_frozen_dataclass(cls, kwargs):
    assert is_dataclass(cls)
    op = cls(**kwargs)
    first_field = fields(cls)[0].name
    with pytest.raises(FrozenInstanceError):
        setattr(op, first_field, "mutated")


@pytest.mark.parametrize("cls,kwargs", _OP_SAMPLES)
def test_op_uses_slots(cls, kwargs):
    op = cls(**kwargs)
    assert hasattr(cls, "__slots__")
    assert not hasattr(op, "__dict__")


@pytest.mark.parametrize("cls,kwargs", _OP_SAMPLES)
def test_op_is_hashable_and_value_equal(cls, kwargs):
    a = cls(**kwargs)
    b = cls(**kwargs)
    assert a == b
    assert hash(a) == hash(b)


def test_op_marker_has_slots_and_no_fields():
    assert hasattr(MemoryOp, "__slots__")
    inst = MemoryOp()
    assert not hasattr(inst, "__dict__")


def test_memory_op_read_level_default_is_detail():
    op = MemoryOpRead(uri="viking://user/memories/x")
    assert op.level == "detail"


def test_memory_op_read_level_literal_values():
    hints = typing.get_type_hints(MemoryOpRead)
    assert set(get_args(hints["level"])) == {"abstract", "overview", "detail"}


def test_memory_op_find_defaults():
    op = MemoryOpFind(query="x")
    assert op.target_uri is None
    assert op.top_k == 8


def test_memory_op_tree_default_depth():
    op = MemoryOpTree(uri="viking://resources/")
    assert op.depth == 2


def test_memory_op_resource_defaults():
    op = MemoryOpResource(source="https://example.com")
    assert op.wait is True
    assert op.timeout_seconds is None


def test_memory_op_commit_defaults():
    op = MemoryOpCommit(
        session_id="s1",
        messages=(("role", "user"),),
    )
    assert op.used_uris == ()
    assert op.wait is False
