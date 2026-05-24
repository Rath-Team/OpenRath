"""OpenViking memory backend adapter (optional ``openrath[openviking]`` extra).

Wraps :class:`openviking.SyncHTTPClient` (HTTP mode) and
:class:`openviking.OpenViking` (embedded mode, conditional on the
``pyagfs`` binding-client wheel being available) behind a
:class:`~rath.memory.MemoryBackend`.

The module imports ``openviking`` lazily; when the extra is missing the
import block at the bottom of :mod:`rath.memory.__init__` swallows the
``ImportError`` and ``OpenVikingBackend`` is simply not registered.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Importing ``openviking`` is what gates this adapter; failures here propagate
# up to ``rath.memory.__init__``'s try/except so the registry stays empty when
# the optional extra is not installed.
import openviking as _ov  # noqa: F401  -- the import itself is the availability check

from rath.memory.abc import MemoryBackend, MemoryStore, MemoryStoreSpec
from rath.memory.capabilities import MemoryCapabilities, ScopeModel
from rath.memory.errors import (
    MemoryBackendError,
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
from rath.memory.registry import register
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

__all__ = ["OpenVikingBackend"]


_CAPABILITIES = MemoryCapabilities(
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

_SUPPORTED_OPS: frozenset[type[MemoryOp]] = frozenset(
    {
        MemoryOpWrite,
        MemoryOpRead,
        MemoryOpList,
        MemoryOpTree,
        MemoryOpFind,
        MemoryOpSearch,
        MemoryOpResource,
        MemoryOpCommit,
    }
)


@dataclass
class _OpenVikingHandle:
    """Internal binding between a :class:`MemoryStore` handle and an SDK client."""

    client: Any
    mode: str  # "http" or "embedded"


@register("openviking")
class OpenVikingBackend(MemoryBackend):
    """:class:`~rath.memory.MemoryBackend` backed by OpenViking 0.3.x."""

    def __init__(self) -> None:
        self._handles: dict[str, _OpenVikingHandle] = {}

    @classmethod
    def is_available(cls) -> bool:
        return True  # Reaching this class means ``import openviking`` succeeded.

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

        url = options.get("url")
        if url:
            try:
                client = _ov.SyncHTTPClient(
                    url=url,
                    api_key=options.get("api_key"),
                    account=spec.account_id or "default",
                    user_id=spec.user_id or "default",
                    agent_id=spec.agent_id or "default",
                    timeout=float(options.get("timeout", 60.0)),
                )
                client.initialize()
            except Exception as exc:  # noqa: BLE001 -- surface real cause
                raise MemoryBackendError(
                    f"failed to open OpenViking HTTP client at {url}: {exc}"
                ) from exc
            mode = "http"
        else:
            path = options.get("path")
            if not path:
                raise MemoryBackendError(
                    "MemoryStoreSpec.options must carry either 'url' (HTTP mode) or "
                    "'path' (embedded mode)"
                )
            try:
                client = _ov.OpenViking(path=str(path))
            except ImportError as exc:
                raise MemoryBackendError(
                    "openviking embedded mode requires the pyagfs binding-client "
                    f"wheel: {exc}"
                ) from exc
            except Exception as exc:  # noqa: BLE001
                raise MemoryBackendError(
                    f"failed to open OpenViking embedded client at {path}: {exc}"
                ) from exc
            mode = "embedded"

        handle = uuid.uuid4().hex
        self._handles[handle] = _OpenVikingHandle(client=client, mode=mode)
        return MemoryStore(backend=self, handle=handle, spec=spec)

    def close(self, store: MemoryStore) -> None:
        if store.closed:
            return
        entry = self._handles.pop(store.handle, None)
        if entry is not None:
            try:
                entry.client.close()
            except Exception:  # noqa: BLE001 -- close must be best-effort
                pass
        store.closed = True

    def dispatch(self, store: MemoryStore, op: MemoryOp) -> MemoryResult:
        if store.closed:
            raise MemoryStoreClosed(store.handle)
        if type(op) not in _SUPPORTED_OPS:
            raise UnsupportedMemoryOp(op_type=type(op), backend_name="openviking")
        client = self._handles[store.handle].client
        try:
            if isinstance(op, MemoryOpRead):
                return self._dispatch_read(client, op)
            if isinstance(op, MemoryOpList):
                return self._dispatch_list(client, op)
            if isinstance(op, MemoryOpTree):
                return self._dispatch_tree(client, op)
            if isinstance(op, MemoryOpFind):
                return self._dispatch_find(client, op)
            if isinstance(op, MemoryOpSearch):
                return self._dispatch_search(client, op)
            if isinstance(op, MemoryOpWrite):
                return self._dispatch_write(client, op)
            if isinstance(op, MemoryOpResource):
                return self._dispatch_resource(client, op)
            if isinstance(op, MemoryOpCommit):
                return self._dispatch_commit(client, op)
        except MemoryStoreClosed:
            raise
        except Exception as exc:  # noqa: BLE001 -- normalize through _failure_from
            return _failure_from(exc)
        raise NotImplementedError(
            f"OpenVikingBackend.dispatch missing branch for {type(op).__name__}"
        )

    # ------------------------------------------------------------------ Write
    @staticmethod
    def _dispatch_write(client: Any, op: "MemoryOpWrite") -> MemoryResult:
        if not _valid_viking_uri(op.uri):
            return MemoryExecutionFailure(
                kind="invalid_uri",
                message=f"unsupported URI scope: {op.uri!r}",
                detail="MemoryOpWrite",
            )
        raw = client.write(
            op.uri,
            op.content,
            mode=op.mode,
            wait=op.wait,
            timeout=op.timeout_seconds,
        )
        written = (
            int(raw["written_bytes"])
            if isinstance(raw, Mapping) and raw.get("written_bytes") is not None
            else len(op.content.encode("utf-8"))
        )
        return MemoryWriteResult(uri=op.uri, bytes_written=written)

    # ------------------------------------------------------------------ Resource
    @staticmethod
    def _dispatch_resource(client: Any, op: "MemoryOpResource") -> MemoryResult:
        raw = client.add_resource(
            op.source,
            to=op.target_uri or None,
            reason=op.reason or "",
            instruction=op.instruction or "",
            wait=op.wait,
            timeout=op.timeout_seconds,
        )
        uri = ""
        if isinstance(raw, Mapping):
            uri = raw.get("root_uri") or raw.get("uri") or (op.target_uri or "")
        return MemoryWriteResult(uri=uri or (op.target_uri or ""), bytes_written=0)

    # ------------------------------------------------------------------ Commit
    @staticmethod
    def _dispatch_commit(client: Any, op: "MemoryOpCommit") -> MemoryResult:
        # create_session is idempotent on this server: returns the existing
        # session if one already exists.
        try:
            client.create_session(session_id=op.session_id)
        except Exception:  # noqa: BLE001 -- tolerate AlreadyExists / similar
            pass
        for msg in op.messages:
            if isinstance(msg, Mapping):
                client.add_message(
                    session_id=op.session_id,
                    role=msg.get("role", "user"),
                    content=msg.get("content"),
                    parts=msg.get("parts"),
                )
            else:
                client.add_message(
                    session_id=op.session_id,
                    role=getattr(msg, "role", "user"),
                    content=getattr(msg, "content", None),
                    parts=getattr(msg, "parts", None),
                )
        raw = client.commit_session(session_id=op.session_id)
        task_id = raw.get("task_id") if isinstance(raw, Mapping) else None
        archived_uri = raw.get("archive_uri") if isinstance(raw, Mapping) else None
        extracted = -1
        if op.wait and op.timeout_seconds:
            try:
                client.wait_processed(timeout=float(op.timeout_seconds))
            except Exception:  # noqa: BLE001
                pass
            if task_id:
                try:
                    task = client.get_task(task_id)
                    if isinstance(task, Mapping):
                        result = task.get("result")
                        if isinstance(result, Mapping):
                            ex = result.get("memories_extracted") or {}
                            if isinstance(ex, Mapping):
                                extracted = int(sum(ex.values())) if ex else 0
                except Exception:  # noqa: BLE001
                    pass
        return MemoryCommitResult(
            task_id=task_id,
            archived_uri=archived_uri,
            extracted_count=extracted,
        )

    # ------------------------------------------------------------------ Read
    @staticmethod
    def _dispatch_read(client: Any, op: "MemoryOpRead") -> MemoryReadResult:
        if op.level == "detail":
            text = client.read(op.uri)
        elif op.level == "abstract":
            text = client.abstract(op.uri)
        elif op.level == "overview":
            text = client.overview(op.uri)
        else:  # pragma: no cover -- Literal protects this branch at type-check time
            raise ValueError(f"unknown read level: {op.level!r}")
        data: str | bytes
        if op.encoding is None:
            data = (text or "").encode("utf-8")
        else:
            data = text or ""
        return MemoryReadResult(uri=op.uri, data=data, level=op.level)

    # ------------------------------------------------------------------ List
    @staticmethod
    def _dispatch_list(client: Any, op: "MemoryOpList") -> MemoryListResult:
        raw = client.ls(op.uri)
        entries = tuple(_entry_from_raw(item) for item in raw)
        return MemoryListResult(entries=entries)

    # ------------------------------------------------------------------ Find/Search
    @staticmethod
    def _dispatch_find(client: Any, op: "MemoryOpFind") -> MemoryFindResult:
        raw = client.find(
            op.query,
            target_uri=op.target_uri or "",
            limit=op.top_k,
        )
        return MemoryFindResult(hits=_hits_from_findresult(raw))

    @staticmethod
    def _dispatch_search(client: Any, op: "MemoryOpSearch") -> MemoryFindResult:
        raw = client.search(
            op.query,
            target_uri=op.target_uri or "",
            session_id=op.session_id,
            limit=op.top_k,
        )
        return MemoryFindResult(hits=_hits_from_findresult(raw))

    # ------------------------------------------------------------------ Tree
    @staticmethod
    def _dispatch_tree(client: Any, op: "MemoryOpTree") -> MemoryListResult:
        raw = client.tree(op.uri)
        flattened: list[MemoryEntry] = []
        _flatten_tree(raw, flattened, base_depth=op.uri.count("/"), max_depth=op.depth)
        return MemoryListResult(entries=tuple(flattened))


_VALID_SCOPES: frozenset[str] = frozenset({"user", "agent", "session", "resources"})


def _valid_viking_uri(uri: str) -> bool:
    """Check that ``uri`` looks like ``viking://{user|agent|session|resources}/...``.

    The server enforces this too (InvalidURIError), but doing a cheap
    client-side check lets us surface a clean ``invalid_uri`` failure
    without burning an HTTP roundtrip on obviously-wrong inputs.
    """
    prefix = "viking://"
    if not uri.startswith(prefix):
        return False
    tail = uri[len(prefix) :]
    head = tail.split("/", 1)[0]
    return head in _VALID_SCOPES


_LEVEL_INT_TO_NAME: dict[int, str] = {0: "abstract", 1: "overview", 2: "detail"}


def _hits_from_findresult(raw: Any) -> tuple[MemoryHit, ...]:
    """Walk an ``openviking.FindResult`` into typed :class:`MemoryHit` tuples.

    The SDK exposes two parallel lists -- ``raw.memories`` and ``raw.resources``
    -- each carrying ``MatchedContext`` objects with ``uri``, ``score``,
    ``abstract``, ``overview``, ``level`` (int 0/1/2).
    """
    matches: list[Any] = []
    for attr in ("memories", "resources", "skills"):
        ms = getattr(raw, attr, None) or []
        matches.extend(ms)
    matches.sort(key=lambda m: getattr(m, "score", 0.0), reverse=True)
    hits: list[MemoryHit] = []
    for m in matches:
        level_raw = getattr(m, "level", None)
        level: Any
        if isinstance(level_raw, int):
            level = _LEVEL_INT_TO_NAME.get(level_raw)
        elif isinstance(level_raw, str):
            level = level_raw if level_raw in _LEVEL_INT_TO_NAME.values() else None
        else:
            level = None
        snippet = getattr(m, "abstract", None) or getattr(m, "overview", None)
        hits.append(
            MemoryHit(
                uri=str(getattr(m, "uri", "")),
                score=float(getattr(m, "score", 0.0)),
                snippet=snippet,
                level=level,
            )
        )
    return tuple(hits)


def _entry_from_raw(item: Mapping[str, Any]) -> MemoryEntry:
    return MemoryEntry(
        name=str(item.get("name", "")),
        uri=str(item.get("uri", "")),
        is_dir=bool(item.get("isDir", False)),
        size=int(item["size"]) if item.get("size") is not None else None,
    )


def _flatten_tree(
    nodes: Any,
    out: list[MemoryEntry],
    base_depth: int,
    max_depth: int | None,
) -> None:
    if not nodes:
        return
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        uri = str(node.get("uri", ""))
        if max_depth is not None and uri.count("/") - base_depth > max_depth:
            continue
        out.append(_entry_from_raw(node))
        children = node.get("children") or node.get("entries")
        if children:
            _flatten_tree(children, out, base_depth, max_depth)


# ---------------------------------------------------------------- error mapping

_KIND_CACHE: dict[type[BaseException], str] | None = None


def _import_exc_classes() -> dict[type[BaseException], str]:
    """Resolve OpenViking exception classes once and memoize the mapping.

    Built from the real ``openviking_cli.exceptions`` module: every class
    here is an actual SDK exception raised by ``SyncHTTPClient``. We do
    NOT include the ``openviking.pyagfs.exceptions`` family because (a)
    they only surface in embedded mode and (b) the SDK normalises pyagfs
    errors to the CLI hierarchy before they reach our dispatch.
    """
    global _KIND_CACHE
    if _KIND_CACHE is not None:
        return _KIND_CACHE
    mapping: dict[type[BaseException], str] = {}
    try:
        from openviking_cli.exceptions import (
            AbortedError,
            AlreadyExistsError,
            ConflictError,
            DeadlineExceededError,
            EmbeddingFailedError,
            FailedPreconditionError,
            InternalError,
            InvalidArgumentError,
            InvalidURIError,
            NotFoundError,
            NotInitializedError,
            PermissionDeniedError,
            ProcessingError,
            ResourceExhaustedError,
            SessionExpiredError,
            UnauthenticatedError,
            UnavailableError,
            UnimplementedError,
            UnsupportedDirectoryFilesError,
            VLMFailedError,
        )

        mapping.update(
            {
                NotFoundError: "not_found",
                InvalidURIError: "invalid_uri",
                InvalidArgumentError: "invalid_uri",
                FailedPreconditionError: "invalid_uri",
                UnsupportedDirectoryFilesError: "invalid_uri",
                PermissionDeniedError: "unauthorized",
                UnauthenticatedError: "unauthorized",
                UnimplementedError: "unsupported",
                NotInitializedError: "unsupported",
                DeadlineExceededError: "timeout",
                UnavailableError: "transport",
                AbortedError: "transport",
                ResourceExhaustedError: "transport",
                ConflictError: "internal",
                AlreadyExistsError: "internal",
                ProcessingError: "extraction_failed",
                EmbeddingFailedError: "extraction_failed",
                VLMFailedError: "extraction_failed",
                SessionExpiredError: "store_closed",
                InternalError: "internal",
            }
        )
    except ImportError:
        pass
    _KIND_CACHE = mapping
    return mapping


def _failure_from(exc: BaseException) -> MemoryExecutionFailure:
    classes = _import_exc_classes()
    for cls, kind in classes.items():
        if isinstance(exc, cls):
            return MemoryExecutionFailure(
                kind=kind,  # type: ignore[arg-type]
                message=str(exc),
                detail=type(exc).__name__,
            )
    if isinstance(exc, TimeoutError):
        return MemoryExecutionFailure(
            kind="timeout", message=str(exc), detail=type(exc).__name__
        )
    if isinstance(exc, ConnectionError):
        return MemoryExecutionFailure(
            kind="transport", message=str(exc), detail=type(exc).__name__
        )
    return MemoryExecutionFailure(
        kind="internal",
        message=str(exc),
        detail=type(exc).__name__,
    )
