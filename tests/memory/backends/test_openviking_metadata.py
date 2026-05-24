"""Metadata-only tests for :class:`OpenVikingBackend` (no live server needed).

These tests still gate on ``openviking`` being importable -- the
``_openviking_canary`` autouse fixture from ``conftest.py`` skips the
module otherwise.
"""

from __future__ import annotations

import pytest

import rath.memory as memory
from rath.memory import ScopeModel
from rath.memory.adapters import openviking as ov_mod

pytestmark = pytest.mark.openviking


def test_backend_name():
    assert ov_mod.OpenVikingBackend.name == "openviking"


def test_is_available_true_when_sdk_importable():
    assert ov_mod.OpenVikingBackend.is_available() is True


def test_capabilities_describe_hybrid_full_surface():
    caps = ov_mod.OpenVikingBackend.capabilities()
    assert caps.scope_model is ScopeModel.HYBRID
    assert caps.supports_write
    assert caps.supports_read
    assert caps.supports_list
    assert caps.supports_tree
    assert caps.supports_vector_search
    assert caps.supports_intent_search
    assert caps.supports_resource_ingest
    assert caps.supports_session_commit
    assert caps.supports_l0_l1_l2


def test_supported_ops_covers_all_eight():
    ops = ov_mod.OpenVikingBackend.supported_ops()
    assert ops == frozenset(
        {
            memory.MemoryOpWrite,
            memory.MemoryOpRead,
            memory.MemoryOpList,
            memory.MemoryOpTree,
            memory.MemoryOpFind,
            memory.MemoryOpSearch,
            memory.MemoryOpResource,
            memory.MemoryOpCommit,
        }
    )


def test_registers_with_registry_on_import():
    assert "openviking" in memory.list_names()
    assert memory.get_class("openviking") is ov_mod.OpenVikingBackend
