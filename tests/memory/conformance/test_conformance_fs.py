"""Cross-backend conformance: shared error and lifecycle behaviour.

These tests run against every registered :class:`MemoryBackend` —
they cover only the contract slice the adapters already agree on:
URI validation, "not found" surfacing, and lifecycle invariants.
Backend-specific semantics (e.g. OpenViking requires pre-seeded
writable memories) live in the per-backend suites.
"""

from __future__ import annotations

import uuid

from rath.memory import MemoryStore
from rath.memory.abc import MemoryBackend
from rath.memory.op_types import MemoryOpRead, MemoryOpWrite
from rath.memory.results import MemoryExecutionFailure


def test_invalid_scope_is_rejected_uniformly(
    conformant_backend: MemoryBackend, conformant_store: MemoryStore
) -> None:
    res = conformant_backend.dispatch(
        conformant_store,
        MemoryOpWrite(uri="viking://bogus_scope_xyz/x", content="x"),
    )
    assert isinstance(res, MemoryExecutionFailure)
    assert res.kind == "invalid_uri"


def test_read_missing_uri_is_not_found(
    conformant_backend: MemoryBackend, conformant_store: MemoryStore
) -> None:
    uri = f"viking://user/default/__nope_{uuid.uuid4().hex}"
    res = conformant_backend.dispatch(conformant_store, MemoryOpRead(uri=uri))
    assert isinstance(res, MemoryExecutionFailure)
    assert res.kind == "not_found"


def test_store_is_open_after_open(
    conformant_backend: MemoryBackend, conformant_store: MemoryStore
) -> None:
    assert conformant_store.closed is False
    assert conformant_store.handle  # non-empty handle


def test_close_is_idempotent(
    conformant_backend: MemoryBackend, conformant_store: MemoryStore
) -> None:
    conformant_backend.close(conformant_store)
    assert conformant_store.closed is True
    # Calling close again must not raise.
    conformant_backend.close(conformant_store)
    assert conformant_store.closed is True
