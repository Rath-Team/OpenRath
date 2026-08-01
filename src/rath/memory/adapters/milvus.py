"""Milvus memory backend adapter (optional ``openrath[milvus]`` extra).

The adapter stores OpenRath memory entries in a Milvus collection and uses
OpenRath's embedding client for vector search. It defaults to Milvus Lite via
``./milvus.db`` and can be pointed at Milvus server or Zilliz Cloud by passing
``uri`` / ``token`` options, or by setting ``MILVUS_URI`` / ``MILVUS_TOKEN``.
"""

from __future__ import annotations

import importlib
import math
import os
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

from pymilvus import DataType, MilvusClient  # type: ignore[import-untyped]

try:  # pragma: no cover - optional across pymilvus versions
    _MilvusException = getattr(
        importlib.import_module("pymilvus.exceptions"),
        "MilvusException",
    )
except ImportError:  # pragma: no cover
    _MilvusException = Exception

from rath.memory.abc import MemoryBackend, MemoryStore, MemoryStoreSpec
from rath.memory.capabilities import MemoryCapabilities, ScopeModel
from rath.memory.errors import (
    MemoryBackendError,
    MemoryStoreClosed,
    UnsupportedMemoryOp,
)
from rath.memory.op_types import (
    MemoryOp,
    MemoryOpFind,
    MemoryOpList,
    MemoryOpRead,
    MemoryOpSearch,
    MemoryOpTree,
    MemoryOpWrite,
)
from rath.memory.registry import register
from rath.memory.results import (
    MemoryEntry,
    MemoryExecutionFailure,
    MemoryFindResult,
    MemoryHit,
    MemoryListResult,
    MemoryReadResult,
    MemoryResult,
    MemoryWriteResult,
)
from rath.memory.uri import (
    MEMORY_URI_PREFIX,
    MEMORY_URI_ROOT,
    memory_uri_prefix,
    to_public_uri,
)

__all__ = ["MilvusMemoryBackend"]


_CAPABILITIES = MemoryCapabilities(
    scope_model=ScopeModel.HYBRID,
    supports_write=True,
    supports_read=True,
    supports_list=True,
    supports_tree=True,
    supports_vector_search=True,
    supports_intent_search=False,
    supports_resource_ingest=False,
    supports_session_commit=False,
    supports_l0_l1_l2=False,
)

_SUPPORTED_OPS: frozenset[type[MemoryOp]] = frozenset(
    {
        MemoryOpWrite,
        MemoryOpRead,
        MemoryOpList,
        MemoryOpTree,
        MemoryOpFind,
        MemoryOpSearch,
    }
)

_VALID_SCOPES: frozenset[str] = frozenset({"user", "agent", "session", "resources"})
_COLLECTION_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,254}$")

_DEFAULT_URI = "./milvus.db"
_DEFAULT_COLLECTION = "openrath_memory"
_DEFAULT_MAX_SCAN = 16384

_URI_FIELD = "uri"
_VECTOR_FIELD = "vector"
_CONTENT_FIELD = "content"
_SCOPE_FIELD = "scope"
_PATH_FIELD = "path"
_NAME_FIELD = "name"
_PARENT_URI_FIELD = "parent_uri"
_CREATED_AT_FIELD = "created_at"
_UPDATED_AT_FIELD = "updated_at"
_METADATA_FIELD = "metadata"

_MAX_URI_LENGTH = 2048
_MAX_PATH_LENGTH = 2048
_MAX_NAME_LENGTH = 512
_MAX_CONTENT_LENGTH = 65535


@dataclass(frozen=True, slots=True)
class _ParsedURI:
    uri: str
    scope: str
    path: str


@dataclass
class _MilvusHandle:
    """Internal binding between a store handle and a Milvus client."""

    client: MilvusClient
    uri: str
    collection_name: str
    options: dict[str, Any]
    drop_on_close: bool = False
    max_scan: int = _DEFAULT_MAX_SCAN
    embedding_client: Any | None = None
    embedding_init_failed: bool = False
    dimension: int | None = None
    collection_ready: bool = False
    schema_checked: bool = False


@register("milvus")
class MilvusMemoryBackend(MemoryBackend):
    """Milvus-backed memory backend using :class:`pymilvus.MilvusClient`."""

    def __init__(self) -> None:
        self._handles: dict[str, _MilvusHandle] = {}

    @classmethod
    def is_available(cls) -> bool:
        return True

    @classmethod
    def capabilities(cls) -> MemoryCapabilities:
        return _CAPABILITIES

    @classmethod
    def supported_ops(cls) -> frozenset[type[MemoryOp]]:
        return _SUPPORTED_OPS

    def store_count(self) -> int:
        return len(self._handles)

    def open(self, spec: MemoryStoreSpec | None = None) -> MemoryStore:
        spec = spec or MemoryStoreSpec()
        options = dict(spec.options or {})
        uri = _string_option(options, "uri", "MILVUS_URI", default=_DEFAULT_URI)
        token = _string_option(
            options, "token", "MILVUS_TOKEN", default=options.get("api_key")
        )
        db_name = _string_option(options, "db_name", "MILVUS_DB_NAME")
        collection_name = _string_option(
            options,
            "collection_name",
            "MILVUS_COLLECTION_NAME",
            default=os.environ.get("MILVUS_COLLECTION") or _DEFAULT_COLLECTION,
        )
        if not _COLLECTION_RE.fullmatch(collection_name):
            raise MemoryBackendError(
                "Milvus collection_name must start with a letter or underscore "
                "and contain only letters, digits, and underscores"
            )

        client_kwargs: dict[str, Any] = {"uri": uri}
        if token:
            client_kwargs["token"] = token
        if db_name:
            client_kwargs["db_name"] = db_name
        try:
            client = MilvusClient(**client_kwargs)
        except Exception as exc:  # noqa: BLE001
            raise MemoryBackendError(
                f"failed to open Milvus client for {uri!r}: {exc}"
            ) from exc

        handle = uuid.uuid4().hex
        self._handles[handle] = _MilvusHandle(
            client=client,
            uri=uri,
            collection_name=collection_name,
            options=options,
            drop_on_close=_bool_option(options, "drop_on_close", default=False),
            max_scan=_int_option(options, "max_scan", default=_DEFAULT_MAX_SCAN),
        )
        return MemoryStore(backend=self, handle=handle, spec=spec)

    def close(self, store: MemoryStore) -> None:
        if store.closed:
            return
        bound = self._handles.pop(store.handle, None)
        if bound is not None:
            if bound.drop_on_close:
                try:
                    if bound.client.has_collection(
                        collection_name=bound.collection_name
                    ):
                        bound.client.drop_collection(
                            collection_name=bound.collection_name
                        )
                except Exception:  # noqa: BLE001
                    pass
            close = getattr(bound.client, "close", None)
            if close is not None:
                try:
                    close()
                except Exception:  # noqa: BLE001
                    pass
        store.closed = True

    def dispatch(self, store: MemoryStore, op: MemoryOp) -> MemoryResult:
        if store.closed:
            raise MemoryStoreClosed(store.handle)
        if type(op) not in _SUPPORTED_OPS:
            raise UnsupportedMemoryOp(op_type=type(op), backend_name="milvus")
        bound = self._handles[store.handle]
        try:
            if isinstance(op, MemoryOpWrite):
                return self._dispatch_write(bound, op)
            if isinstance(op, MemoryOpRead):
                return self._dispatch_read(bound, op)
            if isinstance(op, MemoryOpList):
                return self._dispatch_list(bound, op)
            if isinstance(op, MemoryOpTree):
                return self._dispatch_tree(bound, op)
            if isinstance(op, MemoryOpFind):
                return self._dispatch_find(bound, op)
            if isinstance(op, MemoryOpSearch):
                return self._dispatch_find(
                    bound,
                    MemoryOpFind(
                        query=op.query,
                        target_uri=op.target_uri,
                        top_k=op.top_k,
                    ),
                )
        except MemoryStoreClosed:
            raise
        except Exception as exc:  # noqa: BLE001
            return _failure_from(exc)
        raise AssertionError(f"unreachable dispatch branch for {type(op).__name__}")

    def _dispatch_write(self, bound: _MilvusHandle, op: MemoryOpWrite) -> MemoryResult:
        parsed = _parse_memory_uri(op.uri)
        if isinstance(parsed, MemoryExecutionFailure):
            return parsed
        if op.mode not in ("replace", "write"):
            return MemoryExecutionFailure(
                kind="unsupported",
                message=f"unsupported write mode: {op.mode!r}",
            )
        if len(parsed.uri) > _MAX_URI_LENGTH or len(parsed.path) > _MAX_PATH_LENGTH:
            return MemoryExecutionFailure(
                kind="invalid_uri",
                message="memory URI is too long for the Milvus schema",
            )
        if len(op.content) > _MAX_CONTENT_LENGTH:
            return MemoryExecutionFailure(
                kind="unsupported",
                message=(
                    "memory content exceeds the Milvus VARCHAR limit of "
                    f"{_MAX_CONTENT_LENGTH} characters"
                ),
            )

        vector = _embedding_vector(bound, op.content)
        if isinstance(vector, MemoryExecutionFailure):
            return vector
        ready = _ensure_collection(bound, len(vector))
        if isinstance(ready, MemoryExecutionFailure):
            return ready

        now = int(time.time() * 1000)
        name = _name_for_path(parsed)
        record: dict[str, Any] = {
            _URI_FIELD: parsed.uri,
            _VECTOR_FIELD: vector,
            _CONTENT_FIELD: op.content,
            _SCOPE_FIELD: parsed.scope,
            _PATH_FIELD: parsed.path,
            _NAME_FIELD: name,
            _PARENT_URI_FIELD: _parent_uri(parsed),
            _CREATED_AT_FIELD: now,
            _UPDATED_AT_FIELD: now,
            _METADATA_FIELD: dict(op.metadata or {}),
        }
        bound.client.upsert(collection_name=bound.collection_name, data=[record])
        return MemoryWriteResult(
            uri=parsed.uri,
            bytes_written=len(op.content.encode("utf-8")),
        )

    def _dispatch_read(self, bound: _MilvusHandle, op: MemoryOpRead) -> MemoryResult:
        parsed = _parse_memory_uri(op.uri)
        if isinstance(parsed, MemoryExecutionFailure):
            return parsed
        if not _has_collection(bound):
            return MemoryExecutionFailure(
                kind="not_found",
                message=f"no memory at {parsed.uri}",
            )
        row = _fetch_one(bound, parsed.uri)
        if row is None:
            return MemoryExecutionFailure(
                kind="not_found",
                message=f"no memory at {parsed.uri}",
            )
        text = str(row.get(_CONTENT_FIELD) or "")
        data: str | bytes = text if op.encoding is not None else text.encode("utf-8")
        return MemoryReadResult(uri=parsed.uri, data=data, level=op.level)

    def _dispatch_list(self, bound: _MilvusHandle, op: MemoryOpList) -> MemoryResult:
        parsed = _parse_memory_uri(op.uri)
        if isinstance(parsed, MemoryExecutionFailure):
            return parsed
        if not _has_collection(bound):
            return MemoryListResult(entries=())
        rows = _fetch_rows(bound)
        return MemoryListResult(entries=_list_entries(rows, parsed))

    def _dispatch_tree(self, bound: _MilvusHandle, op: MemoryOpTree) -> MemoryResult:
        parsed = _parse_memory_uri(op.uri)
        if isinstance(parsed, MemoryExecutionFailure):
            return parsed
        if not _has_collection(bound):
            return MemoryListResult(entries=())
        rows = _fetch_rows(bound)
        return MemoryListResult(entries=_tree_entries(rows, parsed, max_depth=op.depth))

    def _dispatch_find(self, bound: _MilvusHandle, op: MemoryOpFind) -> MemoryResult:
        if op.top_k <= 0:
            return MemoryFindResult(hits=())
        target: _ParsedURI | None = None
        if op.target_uri:
            parsed = _parse_memory_uri(op.target_uri)
            if isinstance(parsed, MemoryExecutionFailure):
                return parsed
            target = parsed

        if not _has_collection(bound):
            return MemoryFindResult(hits=())
        vector = _embedding_vector(bound, op.query)
        if isinstance(vector, MemoryExecutionFailure):
            return vector
        ready = _ensure_collection(bound, len(vector), create=False)
        if isinstance(ready, MemoryExecutionFailure):
            return ready

        expr = None
        if target is not None:
            expr = f"{_SCOPE_FIELD} == {_quote_expr_string(target.scope)}"
        limit = min(bound.max_scan, max(op.top_k * 16, op.top_k))
        raw = bound.client.search(
            collection_name=bound.collection_name,
            data=[vector],
            anns_field=_VECTOR_FIELD,
            limit=limit,
            filter=expr,
            output_fields=[
                _URI_FIELD,
                _CONTENT_FIELD,
                _SCOPE_FIELD,
                _PATH_FIELD,
            ],
            search_params={"metric_type": "IP"},
        )
        hits: list[MemoryHit] = []
        for raw_hit in _iter_search_hits(raw):
            entity = raw_hit.get("entity") or raw_hit
            uri = str(entity.get(_URI_FIELD) or raw_hit.get("id") or "")
            content = str(entity.get(_CONTENT_FIELD) or "")
            scope = str(entity.get(_SCOPE_FIELD) or "")
            path = str(entity.get(_PATH_FIELD) or "")
            if target is not None and not _matches_target(scope, path, target):
                continue
            score = float(raw_hit.get("distance", raw_hit.get("score", 0.0)) or 0.0)
            hits.append(
                MemoryHit(
                    uri=uri,
                    score=score,
                    snippet=_snippet(content),
                    level=None,
                )
            )
            if len(hits) >= op.top_k:
                break
        return MemoryFindResult(hits=tuple(hits))


def _ensure_collection(
    bound: _MilvusHandle, dimension: int, *, create: bool = True
) -> MemoryExecutionFailure | None:
    if dimension <= 0:
        return MemoryExecutionFailure(
            kind="internal",
            message="embedding provider returned an empty vector",
        )
    if _has_collection(bound):
        if not bound.schema_checked:
            failure = _validate_collection_schema(bound, expected_dim=dimension)
            if failure is not None:
                return failure
            bound.schema_checked = True
        bound.dimension = dimension
        bound.collection_ready = True
        return None
    if not create:
        return MemoryExecutionFailure(
            kind="not_found",
            message=f"Milvus collection {bound.collection_name!r} does not exist",
        )

    schema = bound.client.create_schema(auto_id=False, enable_dynamic_field=True)
    schema.add_field(
        field_name=_URI_FIELD,
        datatype=DataType.VARCHAR,
        is_primary=True,
        max_length=_MAX_URI_LENGTH,
    )
    schema.add_field(
        field_name=_VECTOR_FIELD,
        datatype=DataType.FLOAT_VECTOR,
        dim=dimension,
    )
    schema.add_field(
        field_name=_CONTENT_FIELD,
        datatype=DataType.VARCHAR,
        max_length=_MAX_CONTENT_LENGTH,
    )
    schema.add_field(
        field_name=_SCOPE_FIELD,
        datatype=DataType.VARCHAR,
        max_length=64,
    )
    schema.add_field(
        field_name=_PATH_FIELD,
        datatype=DataType.VARCHAR,
        max_length=_MAX_PATH_LENGTH,
    )
    schema.add_field(
        field_name=_NAME_FIELD,
        datatype=DataType.VARCHAR,
        max_length=_MAX_NAME_LENGTH,
    )
    schema.add_field(
        field_name=_PARENT_URI_FIELD,
        datatype=DataType.VARCHAR,
        max_length=_MAX_URI_LENGTH,
    )
    schema.add_field(field_name=_CREATED_AT_FIELD, datatype=DataType.INT64)
    schema.add_field(field_name=_UPDATED_AT_FIELD, datatype=DataType.INT64)
    schema.add_field(field_name=_METADATA_FIELD, datatype=DataType.JSON)

    index_params = bound.client.prepare_index_params()
    index_params.add_index(
        field_name=_VECTOR_FIELD,
        index_type="AUTOINDEX",
        metric_type="IP",
    )
    bound.client.create_collection(
        collection_name=bound.collection_name,
        schema=schema,
        index_params=index_params,
    )
    bound.dimension = dimension
    bound.collection_ready = True
    bound.schema_checked = True
    return None


def _validate_collection_schema(
    bound: _MilvusHandle, *, expected_dim: int
) -> MemoryExecutionFailure | None:
    try:
        desc = bound.client.describe_collection(collection_name=bound.collection_name)
    except Exception as exc:  # noqa: BLE001
        return _failure_from(exc)
    fields = _schema_fields(desc)
    names = {_field_name(field) for field in fields}
    missing = {_URI_FIELD, _VECTOR_FIELD, _CONTENT_FIELD} - names
    if missing:
        return MemoryExecutionFailure(
            kind="internal",
            message=(
                f"Milvus collection {bound.collection_name!r} is missing required "
                f"fields: {sorted(missing)}"
            ),
        )
    actual_dim = _vector_dim(fields)
    if actual_dim is not None and actual_dim != expected_dim:
        return MemoryExecutionFailure(
            kind="internal",
            message=(
                f"Milvus collection {bound.collection_name!r} has vector "
                f"dimension {actual_dim}, but the embedding provider returned "
                f"dimension {expected_dim}"
            ),
        )
    return None


def _schema_fields(desc: Any) -> list[Any]:
    if isinstance(desc, dict):
        fields = desc.get("fields")
        if isinstance(fields, list):
            return fields
        schema = desc.get("schema")
        if isinstance(schema, dict) and isinstance(schema.get("fields"), list):
            return list(schema["fields"])
    schema = getattr(desc, "schema", None)
    fields = getattr(schema, "fields", None)
    if isinstance(fields, list):
        return fields
    return []


def _field_name(field: Any) -> str:
    if isinstance(field, dict):
        return str(field.get("name") or field.get("field_name") or "")
    return str(getattr(field, "name", "") or getattr(field, "field_name", ""))


def _vector_dim(fields: list[Any]) -> int | None:
    for field in fields:
        if _field_name(field) != _VECTOR_FIELD:
            continue
        if isinstance(field, dict):
            params = field.get("params")
            if isinstance(params, dict) and params.get("dim") is not None:
                return int(params["dim"])
            if field.get("dim") is not None:
                return int(field["dim"])
        params = getattr(field, "params", None)
        if isinstance(params, dict) and params.get("dim") is not None:
            return int(params["dim"])
        dim = getattr(field, "dim", None)
        if dim is not None:
            return int(dim)
    return None


def _has_collection(bound: _MilvusHandle) -> bool:
    return bool(bound.client.has_collection(collection_name=bound.collection_name))


def _fetch_one(bound: _MilvusHandle, uri: str) -> dict[str, Any] | None:
    rows = bound.client.query(
        collection_name=bound.collection_name,
        filter=f"{_URI_FIELD} == {_quote_expr_string(uri)}",
        output_fields=[
            _URI_FIELD,
            _CONTENT_FIELD,
            _SCOPE_FIELD,
            _PATH_FIELD,
            _NAME_FIELD,
            _PARENT_URI_FIELD,
        ],
        limit=1,
    )
    if not rows:
        return None
    return dict(rows[0])


def _fetch_rows(bound: _MilvusHandle) -> list[dict[str, Any]]:
    rows = bound.client.query(
        collection_name=bound.collection_name,
        filter=f"{_SCOPE_FIELD} != {_quote_expr_string('')}",
        output_fields=[
            _URI_FIELD,
            _CONTENT_FIELD,
            _SCOPE_FIELD,
            _PATH_FIELD,
            _NAME_FIELD,
            _PARENT_URI_FIELD,
        ],
        limit=bound.max_scan,
    )
    return [dict(row) for row in rows]


def _embedding_vector(
    bound: _MilvusHandle, text: str
) -> list[float] | MemoryExecutionFailure:
    client = _maybe_embedding_client(bound)
    if client is None:
        return MemoryExecutionFailure(
            kind="internal",
            message=(
                "Milvus memory requires an embedding provider; pass "
                "MemoryStoreSpec(options={'embedding': client}) or configure "
                "OPENAI_API_KEY / llm.embedding_provider"
            ),
        )
    try:
        raw = client.embed_one(text)
    except Exception as exc:  # noqa: BLE001
        return MemoryExecutionFailure(
            kind="transport",
            message=f"embedding request failed: {exc}",
            detail=type(exc).__name__,
        )
    vector = [float(x) for x in raw]
    if not vector:
        return MemoryExecutionFailure(
            kind="internal",
            message="embedding provider returned an empty vector",
        )
    return _normalize(vector)


def _maybe_embedding_client(bound: _MilvusHandle) -> Any | None:
    if bound.embedding_init_failed:
        return None
    if bound.embedding_client is not None:
        return bound.embedding_client
    pre = bound.options.get("embedding")
    if pre is not None and hasattr(pre, "embed") and hasattr(pre, "embed_one"):
        bound.embedding_client = pre
        return pre

    name = bound.options.get("embedding_provider")
    overrides: dict[str, Any] = {}
    model = bound.options.get("embedding_model")
    if model:
        overrides["model"] = str(model)
    dimensions = bound.options.get("embedding_dimensions")
    if dimensions is not None:
        overrides["dimensions"] = int(dimensions)
    try:
        from rath.llm.embedding import EmbeddingProvider, RathOpenAIEmbeddingClient

        provider = EmbeddingProvider.from_config(
            str(name) if name else None, **overrides
        )
        bound.embedding_client = RathOpenAIEmbeddingClient(provider)
        return bound.embedding_client
    except Exception:  # noqa: BLE001
        bound.embedding_init_failed = True
        return None


def _parse_memory_uri(uri: str) -> _ParsedURI | MemoryExecutionFailure:
    prefix = memory_uri_prefix(uri)
    if prefix is None:
        return MemoryExecutionFailure(
            kind="invalid_uri",
            message=f"URI must start with {MEMORY_URI_PREFIX!r}: {uri!r}",
        )
    public = to_public_uri(uri).rstrip("/")
    if public.rstrip("/") == MEMORY_URI_ROOT.rstrip("/"):
        return MemoryExecutionFailure(
            kind="invalid_uri",
            message="URI has empty path after scheme",
        )
    if not public.startswith(MEMORY_URI_PREFIX):
        return MemoryExecutionFailure(
            kind="invalid_uri",
            message=f"URI must start with {MEMORY_URI_PREFIX!r}: {uri!r}",
        )
    tail = public[len(MEMORY_URI_PREFIX) :]
    if not tail:
        return MemoryExecutionFailure(
            kind="invalid_uri",
            message="URI has empty path after scheme",
        )
    parts = tail.split("/")
    scope = parts[0]
    if scope not in _VALID_SCOPES:
        return MemoryExecutionFailure(
            kind="invalid_uri",
            message=f"unknown scope {scope!r}; must be one of {sorted(_VALID_SCOPES)}",
        )
    rest = parts[1:]
    for seg in rest:
        if seg in ("", ".", ".."):
            return MemoryExecutionFailure(
                kind="invalid_uri",
                message=f"forbidden path segment in {uri!r}",
            )
    path = "/".join(rest)
    normalized = f"{MEMORY_URI_PREFIX}{scope}"
    if path:
        normalized = f"{normalized}/{path}"
    return _ParsedURI(uri=normalized, scope=scope, path=path)


def _parent_uri(parsed: _ParsedURI) -> str:
    if not parsed.path:
        return MEMORY_URI_ROOT
    parent = parsed.path.rsplit("/", 1)[0] if "/" in parsed.path else ""
    if not parent:
        return f"{MEMORY_URI_PREFIX}{parsed.scope}"
    return f"{MEMORY_URI_PREFIX}{parsed.scope}/{parent}"


def _name_for_path(parsed: _ParsedURI) -> str:
    if not parsed.path:
        return parsed.scope
    name = parsed.path.rsplit("/", 1)[-1]
    if len(name) > _MAX_NAME_LENGTH:
        return name[:_MAX_NAME_LENGTH]
    return name


def _list_entries(
    rows: list[dict[str, Any]], base: _ParsedURI
) -> tuple[MemoryEntry, ...]:
    merged: dict[str, MemoryEntry] = {}
    for row in rows:
        item = _entry_under_base(row, base, max_depth=0)
        if item is None:
            continue
        existing = merged.get(item.uri)
        if existing is None or (item.is_dir and not existing.is_dir):
            merged[item.uri] = item
    return tuple(sorted(merged.values(), key=lambda entry: entry.uri))


def _tree_entries(
    rows: list[dict[str, Any]], base: _ParsedURI, *, max_depth: int
) -> tuple[MemoryEntry, ...]:
    merged: dict[str, MemoryEntry] = {}
    for row in rows:
        for depth in range(max(0, max_depth) + 1):
            item = _entry_under_base(row, base, max_depth=depth)
            if item is None:
                continue
            existing = merged.get(item.uri)
            if existing is None or (item.is_dir and not existing.is_dir):
                merged[item.uri] = item
    return tuple(sorted(merged.values(), key=lambda entry: entry.uri))


def _entry_under_base(
    row: dict[str, Any], base: _ParsedURI, *, max_depth: int
) -> MemoryEntry | None:
    scope = str(row.get(_SCOPE_FIELD) or "")
    path = str(row.get(_PATH_FIELD) or "")
    if scope != base.scope:
        return None
    if not _matches_target(scope, path, base):
        return None
    rest = _relative_path(path, base.path)
    if not rest:
        return None
    parts = rest.split("/")
    if max_depth >= len(parts):
        return None
    shown = parts[: max_depth + 1]
    is_leaf = len(shown) == len(parts)
    child_path = "/".join(part for part in (base.path, *shown) if part)
    child_uri = f"{MEMORY_URI_PREFIX}{scope}/{child_path}" if child_path else base.uri
    name = shown[-1]
    size = len(str(row.get(_CONTENT_FIELD) or "").encode("utf-8")) if is_leaf else None
    return MemoryEntry(name=name, uri=child_uri, is_dir=not is_leaf, size=size)


def _relative_path(path: str, prefix: str) -> str:
    if not prefix:
        return path
    if path == prefix:
        return ""
    return path[len(prefix) + 1 :] if path.startswith(prefix + "/") else ""


def _matches_target(scope: str, path: str, target: _ParsedURI) -> bool:
    if scope != target.scope:
        return False
    if not target.path:
        return True
    return path == target.path or path.startswith(target.path + "/")


def _iter_search_hits(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    first = raw[0] if isinstance(raw, list) else raw
    if isinstance(first, list):
        return [dict(item) for item in first]
    return [dict(item) for item in raw]


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0.0:
        return vector
    return [x / norm for x in vector]


def _snippet(body: str, *, max_chars: int = 200) -> str:
    stripped = body.strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[:max_chars].rstrip() + "..."


def _quote_expr_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _string_option(
    options: dict[str, Any],
    key: str,
    env_key: str,
    *,
    default: str | None = None,
) -> str:
    value = options.get(key)
    if value is None:
        value = os.environ.get(env_key)
    if value is None:
        value = default
    return "" if value is None else str(value)


def _bool_option(options: dict[str, Any], key: str, *, default: bool) -> bool:
    value = options.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _int_option(options: dict[str, Any], key: str, *, default: int) -> int:
    value = options.get(key)
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _failure_from(exc: BaseException) -> MemoryExecutionFailure:
    if isinstance(exc, TimeoutError):
        return MemoryExecutionFailure(
            kind="timeout",
            message=str(exc),
            detail=type(exc).__name__,
        )
    if isinstance(exc, ConnectionError):
        return MemoryExecutionFailure(
            kind="transport",
            message=str(exc),
            detail=type(exc).__name__,
        )
    if isinstance(exc, _MilvusException):
        return MemoryExecutionFailure(
            kind="transport",
            message=str(exc),
            detail=type(exc).__name__,
        )
    return MemoryExecutionFailure(
        kind="internal",
        message=str(exc),
        detail=type(exc).__name__,
    )
