"""Value-semantics tests for :mod:`rath.memory.capabilities`."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from enum import Enum

import pytest

from rath.memory.capabilities import MemoryCapabilities, ScopeModel


def test_scope_model_is_str_enum():
    assert issubclass(ScopeModel, str)
    assert issubclass(ScopeModel, Enum)
    assert {m.value for m in ScopeModel} == {"kv", "fs", "vector", "hybrid"}


def test_memory_capabilities_is_frozen_slotted_dataclass():
    assert is_dataclass(MemoryCapabilities)
    cap = _full_cap()
    assert hasattr(MemoryCapabilities, "__slots__")
    assert not hasattr(cap, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cap.supports_write = False  # type: ignore[misc]


def test_memory_capabilities_value_equal_and_hashable():
    a = _full_cap()
    b = _full_cap()
    assert a == b
    assert hash(a) == hash(b)


def test_memory_capabilities_fields_present():
    cap = _full_cap()
    expected = {
        "scope_model",
        "supports_write",
        "supports_read",
        "supports_list",
        "supports_tree",
        "supports_vector_search",
        "supports_intent_search",
        "supports_resource_ingest",
        "supports_session_commit",
        "supports_l0_l1_l2",
    }
    actual = {f.name for f in MemoryCapabilities.__dataclass_fields__.values()}
    assert actual == expected
    # And the constructed value carries our test values.
    assert cap.scope_model is ScopeModel.HYBRID
    assert cap.supports_vector_search is True


def _full_cap() -> MemoryCapabilities:
    return MemoryCapabilities(
        scope_model=ScopeModel.HYBRID,
        supports_write=True,
        supports_read=True,
        supports_list=True,
        supports_tree=True,
        supports_vector_search=True,
        supports_intent_search=True,
        supports_resource_ingest=True,
        supports_session_commit=True,
        supports_l0_l1_l2=True,
    )
