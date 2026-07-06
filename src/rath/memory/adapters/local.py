"""Local filesystem memory backend.

Zero-runtime-dep memory backend so ``pip install openrath`` ships with a
working ``Agent(memory=...)`` path without requiring Docker, OpenViking, or
any extras. Persists every store under
``.openrath/memory/local/<uuid>/`` (see :mod:`rath.memory.persistence`).

Implements the full op surface: FS read/write/list/tree, BM25 and optional
embedding search, resource ingest, and session commit with optional LLM
memo extraction when a chat client is configured.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import math
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rath.memory.abc import MemoryBackend, MemoryStore, MemoryStoreSpec
from rath.memory.capabilities import MemoryCapabilities, ScopeModel
from rath.memory.errors import MemoryStoreClosed, UnsupportedMemoryOp
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
from rath.memory.persistence import (
    PersistentMemoryRegistry,
    ensure_local_memory_root,
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
from rath.memory.uri import (
    LEGACY_MEMORY_URI_PREFIX,
    LEGACY_MEMORY_URI_ROOT,
    MEMORY_URI_PREFIX,
    MEMORY_URI_ROOT,
    memory_uri_prefix,
    to_public_uri,
)
from rath.persistence.atomic import atomic_write_json, atomic_write_text

logger = logging.getLogger(__name__)

__all__ = ["LocalMemoryBackend", "META_SCHEMA_VERSION"]


META_SCHEMA_VERSION = 1
_META_FILENAME = "meta.json"
_VALID_SCOPES: frozenset[str] = frozenset({"user", "agent", "session", "resources"})
_MD_SUFFIX = ".md"
_VEC_SUFFIX = ".vec"
_META_SUFFIX = ".meta.json"
_HIDDEN_SUFFIXES: frozenset[str] = frozenset({_VEC_SUFFIX, _META_SUFFIX})
_DEFAULT_RESOURCE_MAX_BYTES = 10 * 1024 * 1024
_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


_CAPABILITIES = MemoryCapabilities(
    scope_model=ScopeModel.HYBRID,
    supports_write=True,
    supports_read=True,
    supports_list=True,
    supports_tree=True,
    supports_vector_search=True,
    supports_intent_search=False,
    supports_resource_ingest=True,
    supports_session_commit=True,
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
        MemoryOpResource,
        MemoryOpCommit,
    }
)


@dataclass
class _LocalHandle:
    """Internal binding: a :class:`MemoryStore` handle (str path) -> live state."""

    path: Path
    options: dict[str, Any]
    embedding_client: Any | None = None
    embedding_init_failed: bool = field(default=False)
    chat_client: Any | None = None
    chat_init_failed: bool = field(default=False)


@dataclass(frozen=True, slots=True)
class _ResourcePolicy:
    local_roots: tuple[Path, ...]
    allowed_http_hosts: frozenset[str]
    allow_private_hosts: bool
    max_bytes: int


@register("local")
class LocalMemoryBackend(MemoryBackend):
    """Filesystem-backed memory backend, default for ``pip install openrath``."""

    def __init__(self) -> None:
        self._handles: dict[str, _LocalHandle] = {}
        self._registry = PersistentMemoryRegistry()

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

        explicit = options.get("path")
        if explicit:
            path = Path(explicit).expanduser().resolve()
            path.mkdir(parents=True, exist_ok=True)
        else:
            ensure_local_memory_root()
            sid = self._registry.alloc_local_id()
            path = self._registry.local_path(sid).resolve()

        self._touch_meta(path, options=options)

        handle = str(path)
        self._handles[handle] = _LocalHandle(path=path, options=options)
        return MemoryStore(backend=self, handle=handle, spec=spec, closed=False)

    def close(self, store: MemoryStore) -> None:
        if store.closed:
            return
        bound = self._handles.pop(store.handle, None)
        if bound is not None:
            try:
                self._touch_meta(bound.path, options=bound.options, update_only=True)
            except OSError:
                pass
        store.closed = True

    def dispatch(self, store: MemoryStore, op: MemoryOp) -> MemoryResult:
        if store.closed:
            raise MemoryStoreClosed(store.handle)
        if type(op) not in _SUPPORTED_OPS:
            raise UnsupportedMemoryOp(op_type=type(op), backend_name="local")
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
                # Local has no intent model; Search delegates to Find.
                return self._dispatch_find(
                    bound,
                    MemoryOpFind(
                        query=op.query,
                        target_uri=op.target_uri,
                        top_k=op.top_k,
                    ),
                )
            if isinstance(op, MemoryOpResource):
                return self._dispatch_resource(bound, op)
            if isinstance(op, MemoryOpCommit):
                return self._dispatch_commit(bound, op)
        except PermissionError as exc:
            return MemoryExecutionFailure(
                kind="unauthorized",
                message=f"permission denied: {exc}",
            )
        except OSError as exc:
            return MemoryExecutionFailure(
                kind="internal",
                message=f"{type(exc).__name__}: {exc}",
            )
        raise AssertionError(f"unreachable dispatch branch for {type(op).__name__}")

    # ---------------------------------------------------------------- FS handlers

    def _dispatch_write(self, bound: "_LocalHandle", op: MemoryOpWrite) -> MemoryResult:
        resolved = _resolve_uri(bound.path, op.uri)
        if isinstance(resolved, MemoryExecutionFailure):
            return resolved
        if op.mode not in ("replace", "write"):
            return MemoryExecutionFailure(
                kind="unsupported",
                message=f"unsupported write mode: {op.mode!r}",
            )
        target = resolved.with_suffix(_MD_SUFFIX)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = op.content
        atomic_write_text(target, data)
        # Stale embedding/meta sidecars must not persist past a content rewrite.
        for suffix in _HIDDEN_SUFFIXES:
            sidecar = resolved.with_suffix(suffix)
            if sidecar.exists():
                sidecar.unlink()
        return MemoryWriteResult(uri=op.uri, bytes_written=len(data.encode("utf-8")))

    def _dispatch_read(self, bound: "_LocalHandle", op: MemoryOpRead) -> MemoryResult:
        resolved = _resolve_uri(bound.path, op.uri)
        if isinstance(resolved, MemoryExecutionFailure):
            return resolved
        candidates = [resolved.with_suffix(_MD_SUFFIX), resolved]
        target: Path | None = next((c for c in candidates if c.is_file()), None)
        if target is None:
            return MemoryExecutionFailure(
                kind="not_found",
                message=f"no memory at {op.uri}",
            )
        body = target.read_text(encoding="utf-8")
        data: str | bytes
        if op.encoding is None:
            data = body.encode("utf-8")
        else:
            data = body
        return MemoryReadResult(uri=op.uri, data=data, level=op.level)

    def _dispatch_list(self, bound: "_LocalHandle", op: MemoryOpList) -> MemoryResult:
        resolved = _resolve_uri(bound.path, op.uri, must_be_dir=True)
        if isinstance(resolved, MemoryExecutionFailure):
            return resolved
        if not resolved.is_dir():
            return MemoryListResult(entries=())
        return MemoryListResult(entries=_list_dir(resolved, op.uri))

    def _dispatch_find(self, bound: "_LocalHandle", op: MemoryOpFind) -> MemoryResult:
        scope_path, scope_uri = _find_scope(bound.path, op.target_uri)
        if isinstance(scope_path, MemoryExecutionFailure):
            return scope_path
        docs = _collect_md_docs(scope_path, scope_uri)
        if not docs:
            return MemoryFindResult(hits=())

        embed_client = _maybe_embedding_client(bound)
        if embed_client is not None:
            try:
                hits = _embedding_rank(embed_client, docs, op.query, op.top_k)
                return MemoryFindResult(hits=hits)
            except Exception:  # noqa: BLE001 -- degrade silently to lexical
                logger.warning(
                    "LocalMemoryBackend: embedding rank failed; falling back to BM25",
                    exc_info=True,
                )

        hits = _bm25_rank(docs, op.query, op.top_k)
        return MemoryFindResult(hits=hits)

    def _dispatch_tree(self, bound: "_LocalHandle", op: MemoryOpTree) -> MemoryResult:
        resolved = _resolve_uri(bound.path, op.uri, must_be_dir=True)
        if isinstance(resolved, MemoryExecutionFailure):
            return resolved
        if not resolved.is_dir():
            return MemoryListResult(entries=())
        flat: list[MemoryEntry] = []
        _walk_tree(resolved, op.uri, max_depth=op.depth, sink=flat)
        return MemoryListResult(entries=tuple(flat))

    # ---------------------------------------------------------------- Resource

    def _dispatch_resource(
        self, bound: "_LocalHandle", op: MemoryOpResource
    ) -> MemoryResult:
        # Resolve destination dir BEFORE fetching — failures up front.
        target_uri = op.target_uri or f"{MEMORY_URI_PREFIX}resources"
        target_path = _resolve_uri(bound.path, target_uri, must_be_dir=True)
        if isinstance(target_path, MemoryExecutionFailure):
            return target_path

        policy = _resource_policy(bound.options)
        try:
            raw_bytes, original_name, source_label = _fetch_resource(
                op.source,
                policy=policy,
            )
        except FileNotFoundError as exc:
            return MemoryExecutionFailure(
                kind="not_found",
                message=f"resource source not found: {exc}",
            )
        except _ResourceAccessDenied as exc:
            return MemoryExecutionFailure(
                kind="unauthorized",
                message=f"resource source not allowed: {exc}",
            )
        except _ResourceFetchError as exc:
            return MemoryExecutionFailure(
                kind="transport",
                message=f"failed to fetch resource: {exc}",
            )

        sha = hashlib.sha256(raw_bytes).hexdigest()[:16]
        root = target_path / sha
        suffix = Path(original_name).suffix or ".bin"
        blob_path = root / f"source{suffix}"
        meta_path = root / "meta.md"

        if blob_path.is_file() and blob_path.stat().st_size == len(raw_bytes):
            # Dedup: identical content already present — short-circuit.
            return MemoryWriteResult(
                uri=f"{target_uri.rstrip('/')}/{sha}",
                bytes_written=len(raw_bytes),
            )

        root.mkdir(parents=True, exist_ok=True)
        blob_path.write_bytes(raw_bytes)
        meta_lines = [
            f"# Resource {sha}",
            "",
            f"- source: {source_label}",
            f"- original_name: {original_name}",
            f"- bytes: {len(raw_bytes)}",
        ]
        if op.reason:
            meta_lines.extend(["", "## Reason", op.reason])
        if op.instruction:
            meta_lines.extend(["", "## Instruction", op.instruction])
        atomic_write_text(meta_path, "\n".join(meta_lines), newline=True)

        return MemoryWriteResult(
            uri=f"{target_uri.rstrip('/')}/{sha}",
            bytes_written=len(raw_bytes),
        )

    # ---------------------------------------------------------------- Commit

    def _dispatch_commit(
        self, bound: "_LocalHandle", op: MemoryOpCommit
    ) -> MemoryResult:
        if not op.session_id:
            return MemoryExecutionFailure(
                kind="invalid_uri",
                message="MemoryOpCommit requires non-empty session_id",
            )
        session_id = _safe_storage_segment(op.session_id, field="session_id")
        if isinstance(session_id, MemoryExecutionFailure):
            return session_id
        # Archive messages.json under session/<sid>/commits/<timestamp>/.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        commit_root = _contained_child(
            bound.path,
            "session",
            session_id,
            "commits",
            stamp,
        )
        if isinstance(commit_root, MemoryExecutionFailure):
            return commit_root
        commit_root.mkdir(parents=True, exist_ok=True)
        archive_path = commit_root / "messages.json"
        normalized = [_normalize_message(m) for m in op.messages]
        atomic_write_json(archive_path, normalized)
        archived_uri = (
            f"{MEMORY_URI_PREFIX}session/{session_id}/commits/{stamp}/messages.json"
        )

        if not op.wait:
            return MemoryCommitResult(
                task_id=None,
                archived_uri=archived_uri,
                extracted_count=-1,
            )

        chat_client = _maybe_chat_client(bound)
        if chat_client is None:
            return MemoryCommitResult(
                task_id=None,
                archived_uri=archived_uri,
                extracted_count=0,
            )

        extracted = _extract_memos(chat_client, normalized, op.used_uris)
        for uri, content in extracted:
            sub = _resolve_uri(bound.path, uri)
            if isinstance(sub, MemoryExecutionFailure):
                continue
            target = sub.with_suffix(_MD_SUFFIX)
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(target, content)
        return MemoryCommitResult(
            task_id=None,
            archived_uri=archived_uri,
            extracted_count=len(extracted),
        )

    # ---------------------------------------------------------------- helpers

    def _touch_meta(
        self,
        path: Path,
        *,
        options: dict[str, Any],
        update_only: bool = False,
    ) -> None:
        meta_path = path / _META_FILENAME
        now = datetime.now(timezone.utc).isoformat()
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                meta = {}
        else:
            meta = {}
        meta.setdefault("schema_version", META_SCHEMA_VERSION)
        meta.setdefault("created_at", now)
        meta["last_used_at"] = now
        if not update_only:
            meta["embedding_provider"] = options.get("embedding_provider")
            meta["vlm_provider"] = options.get("vlm_provider")
        atomic_write_json(meta_path, meta)


def _resolve_uri(
    store_root: Path, uri: str, *, must_be_dir: bool = False
) -> Path | MemoryExecutionFailure:
    """Map ``memory://{scope}/{rest}`` to a path under ``store_root``.

    Accepts legacy ``viking://`` URIs and normalizes them. Rejects unknown
    scopes, non-memory URIs, and any input that escapes ``store_root`` after
    resolution (path traversal guard). Returns the file path **without** the
    ``.md`` / ``.vec`` suffix — handlers append the right one.
    """
    prefix = memory_uri_prefix(uri)
    if prefix is None:
        return MemoryExecutionFailure(
            kind="invalid_uri",
            message=f"URI must start with {MEMORY_URI_PREFIX!r}: {uri!r}",
        )
    if uri.rstrip("/") in (
        MEMORY_URI_ROOT.rstrip("/"),
        LEGACY_MEMORY_URI_ROOT.rstrip("/"),
    ):
        return MemoryExecutionFailure(
            kind="invalid_uri",
            message="URI has empty path after scheme",
        )
    scheme = (
        MEMORY_URI_PREFIX
        if uri.startswith(MEMORY_URI_PREFIX)
        else LEGACY_MEMORY_URI_PREFIX
    )
    tail = uri[len(scheme) :]
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
            message=(
                f"unknown scope {scope!r}; must be one of {sorted(_VALID_SCOPES)}"
            ),
        )
    rest = parts[1:]
    # Reject empty segments and any traversal token *before* resolving.
    for seg in rest:
        if seg in ("", ".", ".."):
            return MemoryExecutionFailure(
                kind="invalid_uri",
                message=f"forbidden path segment in {uri!r}",
            )
    candidate = store_root.joinpath(scope, *rest)
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        return MemoryExecutionFailure(
            kind="invalid_uri",
            message=f"cannot resolve {uri!r}: {exc}",
        )
    root_resolved = store_root.resolve(strict=False)
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        return MemoryExecutionFailure(
            kind="invalid_uri",
            message=f"path escapes store root: {uri!r}",
        )
    return resolved


def _entry_for(path: Path, uri_base: str) -> MemoryEntry | None:
    """Build a :class:`MemoryEntry` for ``path``; ``None`` if it must be hidden."""
    name = path.name
    if name.endswith(_VEC_SUFFIX):
        return None
    if name == _META_FILENAME:
        return None
    if name.endswith(_META_SUFFIX):
        return None
    if path.is_dir():
        return MemoryEntry(
            name=name,
            uri=f"{uri_base.rstrip('/')}/{name}",
            is_dir=True,
            size=None,
        )
    if name.endswith(_MD_SUFFIX):
        display = name[: -len(_MD_SUFFIX)]
        size = path.stat().st_size if path.exists() else None
        return MemoryEntry(
            name=display,
            uri=f"{uri_base.rstrip('/')}/{display}",
            is_dir=False,
            size=size,
        )
    # Non-markdown files (e.g. resource originals) keep their name verbatim.
    size = path.stat().st_size if path.exists() else None
    return MemoryEntry(
        name=name,
        uri=f"{uri_base.rstrip('/')}/{name}",
        is_dir=False,
        size=size,
    )


def _list_dir(dir_path: Path, uri_base: str) -> tuple[MemoryEntry, ...]:
    entries: list[MemoryEntry] = []
    for child in sorted(dir_path.iterdir()):
        e = _entry_for(child, uri_base)
        if e is not None:
            entries.append(e)
    return tuple(entries)


@dataclass(frozen=True, slots=True)
class _DocRow:
    """One memory document considered for ranking."""

    uri: str
    body: str
    path: Path


def _find_scope(
    store_root: Path, target_uri: str | None
) -> tuple[Path, str] | tuple[MemoryExecutionFailure, str]:
    """Resolve the search scope. ``None``/empty → whole store."""
    if not target_uri:
        return store_root.resolve(strict=False), MEMORY_URI_ROOT
    resolved = _resolve_uri(store_root, target_uri, must_be_dir=True)
    if isinstance(resolved, MemoryExecutionFailure):
        return resolved, target_uri
    return resolved, target_uri.rstrip("/")


def _collect_md_docs(scope_path: Path, scope_uri: str) -> list[_DocRow]:
    """Walk every ``.md`` body under ``scope_path``.

    Iterates the whole store when ``scope_path`` is the store root — handlers
    upstream have already validated that the scope itself is a known one.
    """
    if not scope_path.exists():
        return []
    # When scope_path is the store root, walk its scope subdirs only — the
    # root holds ``meta.json`` we must not surface.
    docs: list[_DocRow] = []
    if scope_uri.rstrip("/") in (
        MEMORY_URI_ROOT.rstrip("/"),
        LEGACY_MEMORY_URI_ROOT.rstrip("/"),
    ):
        for scope in sorted(_VALID_SCOPES):
            sub = scope_path / scope
            if sub.is_dir():
                _walk_md(sub, f"{MEMORY_URI_PREFIX}{scope}", docs)
        return docs
    if scope_path.is_file():
        # Caller pointed at a single memory.
        text = _safe_read(scope_path)
        if text is not None:
            docs.append(_DocRow(uri=scope_uri, body=text, path=scope_path))
        return docs
    _walk_md(scope_path, scope_uri, docs)
    return docs


def _walk_md(dir_path: Path, uri_base: str, sink: list[_DocRow]) -> None:
    for child in sorted(dir_path.iterdir()):
        name = child.name
        if (
            name == _META_FILENAME
            or name.endswith(_VEC_SUFFIX)
            or name.endswith(_META_SUFFIX)
        ):
            continue
        if child.is_dir():
            _walk_md(child, f"{uri_base.rstrip('/')}/{name}", sink)
            continue
        if not name.endswith(_MD_SUFFIX):
            continue
        body = _safe_read(child)
        if body is None:
            continue
        display = name[: -len(_MD_SUFFIX)]
        sink.append(
            _DocRow(
                uri=f"{uri_base.rstrip('/')}/{display}",
                body=body,
                path=child,
            )
        )


def _safe_read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text) if t]


def _snippet(body: str, *, max_chars: int = 200) -> str:
    stripped = body.strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[:max_chars].rstrip() + "..."


def _bm25_rank(docs: list[_DocRow], query: str, top_k: int) -> tuple[MemoryHit, ...]:
    """Classic BM25 (k1=1.5, b=0.75) over tokenized doc bodies."""
    query_terms = _tokenize(query)
    if not query_terms:
        return ()
    tokenized = [(d, _tokenize(d.body)) for d in docs]
    N = len(tokenized)
    if N == 0:
        return ()
    avgdl = sum(len(toks) for _, toks in tokenized) / N if N else 0.0
    # Document frequency per term.
    df: dict[str, int] = {}
    for _, toks in tokenized:
        for term in set(toks):
            df[term] = df.get(term, 0) + 1
    k1 = 1.5
    b = 0.75
    scored: list[tuple[float, _DocRow]] = []
    for doc, toks in tokenized:
        if not toks:
            scored.append((0.0, doc))
            continue
        dl = len(toks)
        score = 0.0
        for term in query_terms:
            tf = sum(1 for t in toks if t == term)
            if tf == 0:
                continue
            n_qi = df.get(term, 0)
            idf = math.log(1 + (N - n_qi + 0.5) / (n_qi + 0.5))
            denom = tf + k1 * (1 - b + b * (dl / avgdl if avgdl else 1.0))
            score += idf * (tf * (k1 + 1)) / denom if denom else 0.0
        scored.append((score, doc))
    scored.sort(key=lambda row: row[0], reverse=True)
    top = scored[: max(0, top_k)]
    return tuple(
        MemoryHit(
            uri=doc.uri,
            score=float(score),
            snippet=_snippet(doc.body),
            level=None,
        )
        for score, doc in top
    )


def _embedding_rank(
    client: Any, docs: list[_DocRow], query: str, top_k: int
) -> tuple[MemoryHit, ...]:
    """Cosine-similarity ranking using a precomputed ``.vec`` sidecar per doc.

    Sidecars are JSON files holding ``{"model": ..., "vector": [floats...]}``;
    missing sidecars are recomputed in-place. The query embedding is computed
    fresh on every call.
    """
    if not docs:
        return ()
    model = getattr(client.provider, "model", None) or "<embedding>"
    # Ensure every doc has an up-to-date sidecar.
    need_embed: list[_DocRow] = []
    cached: dict[Path, list[float]] = {}
    for doc in docs:
        sidecar = doc.path.with_suffix(_VEC_SUFFIX)
        vec = _load_vec(sidecar, expected_model=model)
        if vec is None:
            need_embed.append(doc)
        else:
            cached[doc.path] = vec
    if need_embed:
        new_vecs = client.embed(tuple(d.body for d in need_embed))
        for doc, vec in zip(need_embed, new_vecs):
            _store_vec(doc.path.with_suffix(_VEC_SUFFIX), model, vec)
            cached[doc.path] = list(vec)
    query_vec = client.embed_one(query)
    scored: list[tuple[float, _DocRow]] = []
    for doc in docs:
        vec = cached.get(doc.path)
        if vec is None:
            continue
        scored.append((_cosine(query_vec, vec), doc))
    scored.sort(key=lambda row: row[0], reverse=True)
    top = scored[: max(0, top_k)]
    return tuple(
        MemoryHit(
            uri=doc.uri,
            score=float(score),
            snippet=_snippet(doc.body),
            level=None,
        )
        for score, doc in top
    )


def _load_vec(sidecar: Path, *, expected_model: str) -> list[float] | None:
    if not sidecar.is_file():
        return None
    try:
        raw = json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(raw, dict):
        return None
    if raw.get("model") != expected_model:
        return None
    vec = raw.get("vector")
    if not isinstance(vec, list):
        return None
    try:
        return [float(x) for x in vec]
    except (TypeError, ValueError):
        return None


def _store_vec(sidecar: Path, model: str, vec: Any) -> None:
    payload = {"model": model, "vector": [float(x) for x in vec]}
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(sidecar, payload, indent=None)


def _cosine(u: Any, v: list[float]) -> float:
    if u is None or v is None:
        return 0.0
    u_list = list(u)
    if not u_list or not v:
        return 0.0
    dot = sum(a * b for a, b in zip(u_list, v))
    nu = math.sqrt(sum(a * a for a in u_list))
    nv = math.sqrt(sum(b * b for b in v))
    if nu == 0.0 or nv == 0.0:
        return 0.0
    return float(dot / (nu * nv))


def _maybe_chat_client(bound: "_LocalHandle") -> Any | None:
    """Lazily build a chat client for commit extraction; ``None`` if unset.

    Reads ``options.chat`` (pre-built client) first, then
    ``options.chat_provider`` (``llm.providers`` name via
    :meth:`~rath.llm.Provider.from_config`).
    """
    if bound.chat_init_failed:
        return None
    if bound.chat_client is not None:
        return bound.chat_client
    pre = bound.options.get("chat")
    if pre is not None and hasattr(pre, "complete"):
        bound.chat_client = pre
        return pre
    name = bound.options.get("chat_provider")
    if not name:
        bound.chat_init_failed = True
        return None
    try:
        from rath.llm import Provider, chat_client_for

        provider = Provider.from_config(name)
        bound.chat_client = chat_client_for(provider)
        return bound.chat_client
    except Exception:  # noqa: BLE001 — commit extraction degrades to archive-only
        logger.info(
            "LocalMemoryBackend: chat provider unavailable, skipping memo extraction",
            exc_info=True,
        )
        bound.chat_init_failed = True
        return None


def _maybe_embedding_client(bound: "_LocalHandle") -> Any | None:
    """Lazily build an embedding client for ``bound``; ``None`` if not configured.

    Reads ``options.embedding_provider`` first, then falls back to
    ``options.embedding`` (an already-built client / provider). Failure to
    initialize is cached so subsequent dispatches degrade silently.
    """
    if bound.embedding_init_failed:
        return None
    if bound.embedding_client is not None:
        return bound.embedding_client
    # Pre-built client passed in spec.options["embedding"].
    pre = bound.options.get("embedding")
    if pre is not None and hasattr(pre, "embed") and hasattr(pre, "embed_one"):
        bound.embedding_client = pre
        return pre

    name = bound.options.get("embedding_provider")
    if not name and pre is None:
        bound.embedding_init_failed = True
        return None
    try:
        from rath.llm.embedding import EmbeddingProvider, RathOpenAIEmbeddingClient

        provider = EmbeddingProvider.from_config(name)
        client = RathOpenAIEmbeddingClient(provider)
        bound.embedding_client = client
        return client
    except Exception:  # noqa: BLE001 -- degrade to BM25 silently
        logger.info(
            "LocalMemoryBackend: embedding provider unavailable, using BM25 fallback",
            exc_info=True,
        )
        bound.embedding_init_failed = True
        return None


def _normalize_message(msg: Any) -> dict[str, Any]:
    """Coerce a message-like object into ``{role, content, ...}`` for archive."""
    if isinstance(msg, dict):
        return {k: v for k, v in msg.items()}
    out: dict[str, Any] = {}
    if hasattr(msg, "role"):
        out["role"] = getattr(msg, "role")
    if hasattr(msg, "content"):
        out["content"] = getattr(msg, "content")
    if hasattr(msg, "parts"):
        parts = getattr(msg, "parts")
        if parts is not None:
            out["parts"] = parts
    return out


_EXTRACTION_PROMPT = """\
You are a memory extractor. From the conversation below, extract durable
facts about the user that would be useful to remember in future sessions
(preferences, profile, recurring projects). Skip transient task context.

Return STRICT JSON: an array of objects with two string keys:
- "uri": a memory://user/memories/extracted/<slug> URI
- "content": one-sentence English memo

If no durable facts are present, return [].
"""


def _extract_memos(
    chat_client: Any,
    messages: list[dict[str, Any]],
    used_uris: Any,
) -> list[tuple[str, str]]:
    """Ask the chat client for a JSON array of memos; tolerate any error."""
    try:
        from rath.llm.chat_request import RathLLMChatRequest, RathLLMMessage
    except Exception:  # noqa: BLE001
        return []
    convo_lines = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content")
        if content is None:
            parts = msg.get("parts") or []
            content = " ".join(str(p) for p in parts)
        convo_lines.append(f"[{role}] {content}")
    convo = "\n".join(convo_lines)
    req = RathLLMChatRequest(
        messages=(
            RathLLMMessage(role="system", content=_EXTRACTION_PROMPT),
            RathLLMMessage(
                role="user",
                content=f"Conversation:\n{convo}\n\nReturn the JSON array now.",
            ),
        ),
        temperature=0.0,
    )
    try:
        resp = chat_client.complete(req)
    except Exception:  # noqa: BLE001 -- network/transport surfaced as zero memos
        logger.warning("LocalMemoryBackend: chat extraction failed", exc_info=True)
        return []
    raw = _extract_response_text(resp)
    payload = _coerce_json_array(raw)
    out: list[tuple[str, str]] = []
    if not isinstance(payload, list):
        return out
    for item in payload:
        if not isinstance(item, dict):
            continue
        uri = item.get("uri")
        content = item.get("content")
        if not isinstance(uri, str) or not isinstance(content, str):
            continue
        if memory_uri_prefix(uri) is None:
            continue
        out.append((to_public_uri(uri), content))
    return out


def _extract_response_text(resp: Any) -> str:
    """Pull the assistant text content from a chat response, tolerantly."""
    if resp is None:
        return ""
    direct = getattr(resp, "content", None)
    if isinstance(direct, str):
        return direct
    choices = getattr(resp, "choices", None)
    if choices:
        try:
            choice = choices[0]
        except (IndexError, TypeError):
            return ""
        msg = getattr(choice, "message", None)
        if msg is not None:
            content = getattr(msg, "content", None)
            if isinstance(content, str):
                return content
    return ""


def _coerce_json_array(text: str) -> Any:
    """Best-effort: extract the first JSON array from ``text``."""
    text = text.strip()
    if not text:
        return None
    # Strip ```json fences if present.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


class _ResourceFetchError(Exception):
    """Wraps transport errors when fetching a remote resource."""


class _ResourceAccessDenied(Exception):
    """Raised when a resource source violates the configured policy."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Reject redirects so each fetched URL is policy-checked directly."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirect)


def _resource_policy(options: dict[str, Any]) -> _ResourcePolicy:
    roots = tuple(
        Path(p).expanduser().resolve(strict=False)
        for p in _option_strings(options.get("resource_import_roots"))
    )
    hosts = frozenset(
        h.lower() for h in _option_strings(options.get("resource_allowed_http_hosts"))
    )
    raw_max = options.get("resource_max_bytes", _DEFAULT_RESOURCE_MAX_BYTES)
    try:
        max_bytes = int(raw_max)
    except (TypeError, ValueError):
        max_bytes = _DEFAULT_RESOURCE_MAX_BYTES
    return _ResourcePolicy(
        local_roots=roots,
        allowed_http_hosts=hosts,
        allow_private_hosts=bool(options.get("resource_allow_private_hosts", False)),
        max_bytes=max(1, max_bytes),
    )


def _option_strings(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw,)
    try:
        return tuple(str(x) for x in raw)
    except TypeError:
        return (str(raw),)


def _fetch_resource(
    source: str,
    *,
    policy: _ResourcePolicy,
) -> tuple[bytes, str, str]:
    """Resolve ``source`` to ``(bytes, original_name, source_label)``.

    Local paths and HTTP(S) URLs are disabled by default. Callers must opt in
    with ``resource_import_roots`` or ``resource_allowed_http_hosts`` in the
    store options so untrusted resource ingest cannot read host files or SSRF
    internal services.
    """
    parsed = urllib.parse.urlparse(source)
    scheme = parsed.scheme.lower()
    # Windows drive letters look like ``c:\foo`` to urlparse — treat as path.
    if len(scheme) == 1 and scheme.isalpha():
        scheme = ""
    if scheme in ("http", "https"):
        _validate_resource_url(parsed, policy=policy)
        try:
            with _NO_REDIRECT_OPENER.open(source, timeout=30) as resp:
                raw_len = resp.headers.get("Content-Length")
                if raw_len is not None and int(raw_len) > policy.max_bytes:
                    raise _ResourceFetchError(
                        f"resource exceeds {policy.max_bytes} bytes",
                    )
                data = resp.read(policy.max_bytes + 1)
        except urllib.error.URLError as exc:
            raise _ResourceFetchError(str(exc)) from exc
        except ValueError as exc:
            raise _ResourceFetchError(str(exc)) from exc
        if len(data) > policy.max_bytes:
            raise _ResourceFetchError(f"resource exceeds {policy.max_bytes} bytes")
        name = Path(parsed.path).name or "resource"
        return data, name, source
    if scheme == "file":
        local = Path(urllib.request.url2pathname(parsed.path))
    elif scheme in ("", None):
        local = Path(source)
    else:
        raise _ResourceFetchError(f"unsupported scheme: {scheme!r}")
    local = local.expanduser().resolve(strict=False)
    _validate_local_resource_path(local, policy=policy)
    if not local.is_file():
        raise FileNotFoundError(str(local))
    size = local.stat().st_size
    if size > policy.max_bytes:
        raise _ResourceFetchError(f"resource exceeds {policy.max_bytes} bytes")
    return local.read_bytes(), local.name, str(local)


def _validate_local_resource_path(local: Path, *, policy: _ResourcePolicy) -> None:
    if not policy.local_roots:
        raise _ResourceAccessDenied("local paths require resource_import_roots")
    for root in policy.local_roots:
        try:
            local.relative_to(root)
        except ValueError:
            continue
        return
    raise _ResourceAccessDenied(f"{local} is outside resource_import_roots")


def _validate_resource_url(
    parsed: urllib.parse.ParseResult,
    *,
    policy: _ResourcePolicy,
) -> None:
    host = (parsed.hostname or "").lower()
    if not host:
        raise _ResourceAccessDenied("HTTP(S) resource URL requires a host")
    if host not in policy.allowed_http_hosts:
        raise _ResourceAccessDenied("HTTP(S) host is not allowed")
    try:
        infos = socket.getaddrinfo(
            host,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise _ResourceFetchError(str(exc)) from exc
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise _ResourceAccessDenied(f"cannot validate address {address!r}") from exc
        if _is_restricted_address(ip) and not policy.allow_private_hosts:
            raise _ResourceAccessDenied("HTTP(S) host resolves to a private address")


def _is_restricted_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _safe_storage_segment(value: str, *, field: str) -> str | MemoryExecutionFailure:
    text = str(value)
    if not text or text in (".", "..") or not _SAFE_SEGMENT_RE.fullmatch(text):
        return MemoryExecutionFailure(
            kind="invalid_uri",
            message=f"{field} must be a single safe path segment",
        )
    return text


def _contained_child(
    root: Path,
    *parts: str,
) -> Path | MemoryExecutionFailure:
    try:
        resolved = root.joinpath(*parts).resolve(strict=False)
        resolved.relative_to(root.resolve(strict=False))
    except (OSError, ValueError) as exc:
        return MemoryExecutionFailure(
            kind="invalid_uri",
            message=f"path escapes store root: {exc}",
        )
    return resolved


def _walk_tree(
    dir_path: Path,
    uri_base: str,
    *,
    max_depth: int,
    sink: list[MemoryEntry],
    _depth: int = 0,
) -> None:
    """Pre-order walk emitting one :class:`MemoryEntry` per visible node.

    ``max_depth=0`` lists only the immediate children of ``dir_path``;
    ``max_depth=N`` recurses N additional levels.
    """
    if _depth > max_depth:
        return
    for child in sorted(dir_path.iterdir()):
        entry = _entry_for(child, uri_base)
        if entry is None:
            continue
        sink.append(entry)
        if entry.is_dir and _depth < max_depth:
            _walk_tree(
                child,
                entry.uri,
                max_depth=max_depth,
                sink=sink,
                _depth=_depth + 1,
            )
