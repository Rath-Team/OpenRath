"""Public :mod:`rath.memory` API: memory backends, op types, results, registry.

The memory plane is parallel to :mod:`rath.backend`: every concept here mirrors
a sibling there (``MemoryBackend`` <-> ``Backend``, ``MemoryStore`` <->
``BackendSandbox``, ``MemoryOp*`` <-> ``BackendTool*``, ``MemoryResult`` <->
``ToolResult``). The two planes never cross-import -- :class:`rath.flow.Agent`
holds both.

Optional adapters (e.g. ``OpenVikingBackend``) live in
:mod:`rath.memory.adapters` and self-register on import. They are gated behind
optional extras (``openrath[openviking]``); importing :mod:`rath.memory`
without those extras leaves the registry empty.
"""

from __future__ import annotations

from rath.memory.abc import MemoryBackend, MemoryStore, MemoryStoreSpec

# Local backend ships with the base install — always registered.
from rath.memory.adapters import local as _local  # noqa: F401
from rath.memory.capabilities import MemoryCapabilities, ScopeModel
from rath.memory.errors import (
    MemoryBackendError,
    MemoryBackendNotFound,
    MemoryConflict,
    MemoryNotFound,
    MemoryStoreClosed,
    UnsupportedMemoryOp,
)
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
from rath.memory.registry import (
    current,
    get,
    get_class,
    is_available,
    list_names,
    preferred,
    register,
    set_default,
)
from rath.memory.registry import set_default as _set_default
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

try:
    from rath.memory.adapters import openviking as _openviking  # noqa: F401
except ImportError:  # pragma: no cover -- optional ``openviking`` extra
    pass

# The local backend has zero runtime dependencies; pin it as the default
# so ``rath.memory.current()`` works out of the box.
_set_default("local")

__all__ = [
    "MemoryBackend",
    "MemoryStore",
    "MemoryStoreSpec",
    "MemoryCapabilities",
    "ScopeModel",
    "MemoryOp",
    "MemoryOpWrite",
    "MemoryOpRead",
    "MemoryOpList",
    "MemoryOpTree",
    "MemoryOpFind",
    "MemoryOpSearch",
    "MemoryOpResource",
    "MemoryOpCommit",
    "MemoryResult",
    "MemoryHit",
    "MemoryEntry",
    "MemoryFindResult",
    "MemoryReadResult",
    "MemoryListResult",
    "MemoryWriteResult",
    "MemoryCommitResult",
    "MemoryExecutionFailure",
    "MemoryBackendError",
    "MemoryBackendNotFound",
    "MemoryStoreClosed",
    "UnsupportedMemoryOp",
    "MemoryNotFound",
    "MemoryConflict",
    "register",
    "list_names",
    "get",
    "get_class",
    "is_available",
    "preferred",
    "set_default",
    "current",
]
