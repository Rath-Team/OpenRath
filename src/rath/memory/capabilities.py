"""Static memory-backend capability description (mirrors :mod:`rath.backend.capabilities`)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = ["ScopeModel", "MemoryCapabilities"]


class ScopeModel(str, Enum):
    """How a memory backend organises its keyspace."""

    KV = "kv"
    FS = "fs"
    VECTOR = "vector"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class MemoryCapabilities:
    """Static, class-level capability description for a memory backend."""

    scope_model: ScopeModel
    supports_write: bool
    supports_read: bool
    supports_list: bool
    supports_tree: bool
    supports_vector_search: bool
    supports_intent_search: bool
    supports_resource_ingest: bool
    supports_session_commit: bool
    supports_l0_l1_l2: bool
