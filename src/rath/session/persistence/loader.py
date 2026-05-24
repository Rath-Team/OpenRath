"""Read-side counterpart to :mod:`rath.session.persistence.writer`.

Functions:

* :func:`load_session` — parse a session file into :class:`PersistedSession`.
* :func:`list_persisted_sessions` — enumerate meta-data for every session
  file in the resolved sessions directory.

Both round-trip through pure JSON; no live sandbox is opened. A persisted
session can be revived for replay via :meth:`PersistedSession.to_resumable_pair`
which returns ``(user_session, agent_session)`` suitable as inputs to
:func:`~rath.session.loop.run_session_loop`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from rath.backend.abc import BackendSandboxSpec
from rath.llm.chat_response import RathLLMTokenUsage
from rath.session.chunk import ChunkKind, ChunkRow, ChunkTable
from rath.session.graph.kind import LineageKind
from rath.session.persistence._migrations import (
    CURRENT_SCHEMA_VERSION,
    upgrade_chunk,
    upgrade_header,
)
from rath.session.persistence._serialize import (
    coerce_lineage_kind,
    lineage_extras_from_jsonable,
    parse_uuid_list,
    spec_from_jsonable,
    usage_from_jsonable,
)
from rath.session.persistence.errors import PersistenceError
from rath.session.persistence.paths import (
    SESSION_FILE_SUFFIX,
    SESSION_PARTIAL_SUFFIX,
    session_file,
    session_partial_file,
    sessions_dir,
)
from rath.session.session import Session

__all__ = [
    "PersistedSessionHeader",
    "PersistedSessionMeta",
    "PersistedSession",
    "load_session",
    "list_persisted_sessions",
    "delete_session",
    "prune_sessions",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True, slots=True)
class PersistedSessionHeader:
    """The ``record_type=header`` line, decoded."""

    schema_version: int
    id: UUID
    created_at: datetime
    parent_session_ids: tuple[UUID, ...]
    lineage_operator: str
    lineage_kind: LineageKind
    lineage_extras: tuple[tuple[str, Any], ...]
    sandbox_backend: str | None
    sandbox_spec: BackendSandboxSpec | None
    sandbox_handle_id: str | None


@dataclass(frozen=True, kw_only=True, slots=True)
class PersistedSessionMeta:
    """Lightweight summary used by :func:`list_persisted_sessions`.

    Reading meta is cheap: only the header (line 1) is parsed, the rest of
    the file is scanned only to count chunks and detect a trailer.
    """

    id: UUID
    path: Path
    created_at: datetime
    lineage_operator: str
    lineage_kind: LineageKind
    chunk_count: int
    closed: bool


@dataclass(frozen=True, kw_only=True, slots=True)
class PersistedSession:
    """Full round-trip view of one persisted session file."""

    header: PersistedSessionHeader
    chunk_table: ChunkTable
    cumulative_usage: RathLLMTokenUsage | None
    closed: bool
    path: Path
    trailer_raw: dict[str, Any] | None = field(default=None, repr=False)

    def to_resumable_pair(
        self, *, agent_prompt: str | None = None
    ) -> tuple[Session, Session]:
        """Build ``(user_session, agent_session)`` ready for ``run_session_loop``.

        The user session inherits the persisted chunk_table verbatim (so the
        loop sees the same transcript). The agent session carries the system
        prompt (if any) extracted from the persisted history, or
        ``agent_prompt`` if provided to override.

        Sandbox handling depends on the recorded backend:

        * ``opensandbox`` with a ``sandbox_handle_id`` — reattach immediately
          via :meth:`PersistentSandboxRegistry.reattach_remote` so the
          resumed session targets the same remote container instead of
          spinning up a fresh one. Performs I/O against the registry index
          file and the OpenSandbox backend's ``attach``.
        * Local (or no recorded handle) — keep the spec on the unbound
          session; the next consumer opens lazily.
        """
        user = Session(
            chunk_table=self.chunk_table,
            sandbox_backend=self.header.sandbox_backend,
            _sandbox_open_spec=self.header.sandbox_spec,
        )

        if (
            self.header.sandbox_backend == "opensandbox"
            and self.header.sandbox_handle_id
        ):
            from rath.backend.persistence.registry import PersistentSandboxRegistry

            try:
                handle_uuid = UUID(self.header.sandbox_handle_id)
            except ValueError:
                handle_uuid = None
            if handle_uuid is not None:
                sandbox = PersistentSandboxRegistry().reattach_remote(handle_uuid)
                user.bind_sandbox(sandbox)

        if agent_prompt is not None:
            agent = Session.from_agent_prompt(agent_prompt)
        else:
            system_text = _extract_system_prompt(self.chunk_table)
            agent = (
                Session.from_agent_prompt(system_text)
                if system_text is not None
                else Session(chunk_table=ChunkTable(rows=()))
            )

        return user, agent


def load_session(
    session_id: UUID | str, *, path: Path | None = None
) -> PersistedSession:
    """Parse one session JSONL into a :class:`PersistedSession`.

    Pass ``session_id`` to look up under the resolved sessions directory, or
    ``path`` to read an explicit file (mainly for tests). The two are
    mutually exclusive — when both are given, ``path`` wins.

    Raises :class:`PersistenceError` for malformed JSON, missing header, or
    schema-version mismatches. A trailing unterminated line is treated as a
    crashed-mid-write line and silently skipped; the returned
    :attr:`PersistedSession.closed` field will be ``False`` because no
    trailer record was observed.
    """
    target = (path or session_file(session_id)).resolve()
    if not target.is_file():
        # Fall back to the in-flight WAL file. Callers usually want the
        # final file but a crashed/abandoned session only leaves behind
        # ``<id>.jsonl.__partial__``; surfacing that is more useful than a
        # "not found" error.
        if path is None:
            partial = session_partial_file(session_id).resolve()
            if partial.is_file():
                target = partial
            else:
                raise PersistenceError(f"persisted session file not found: {target}")
        else:
            raise PersistenceError(f"persisted session file not found: {target}")

    header: PersistedSessionHeader | None = None
    header_origin_version: int = CURRENT_SCHEMA_VERSION
    rows: list[ChunkRow] = []
    trailer: dict[str, Any] | None = None
    cumulative_usage: RathLLMTokenUsage | None = None

    try:
        text = target.read_text(encoding="utf-8")
    except OSError as e:
        raise PersistenceError(f"failed to read {target}: {e}") from e

    for lineno, raw_line in enumerate(text.splitlines(keepends=True), start=1):
        if not raw_line.endswith("\n"):
            # Partial final line — almost certainly a crashed write. Drop it.
            continue
        line = raw_line.rstrip("\n").strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as e:
            raise PersistenceError(
                f"{target}:{lineno}: invalid JSON (col {e.colno}): {e.msg}",
            ) from e
        if not isinstance(record, dict):
            raise PersistenceError(
                f"{target}:{lineno}: record must be a JSON object, got "
                f"{type(record).__name__}",
            )
        rt = record.get("record_type")
        if rt == "header":
            if header is not None:
                raise PersistenceError(
                    f"{target}:{lineno}: duplicate header record",
                )
            header_origin_version = int(record.get("schema_version", 0))
            try:
                record = upgrade_header(record)
            except ValueError as e:
                raise PersistenceError(f"{target}:{lineno}: {e}") from e
            header = _header_from_record(record, path=target, lineno=lineno)
        elif rt == "chunk":
            if header is None:
                raise PersistenceError(
                    f"{target}:{lineno}: chunk record before header",
                )
            record = upgrade_chunk(record, header_version=header_origin_version)
            rows.append(_chunk_from_record(record, path=target, lineno=lineno))
        elif rt == "trailer":
            trailer = record
            cumulative_usage = usage_from_jsonable(record.get("cumulative_usage"))
        else:
            raise PersistenceError(
                f"{target}:{lineno}: unknown record_type={rt!r}",
            )

    if header is None:
        raise PersistenceError(f"{target}: no header record found")

    return PersistedSession(
        header=header,
        chunk_table=ChunkTable(rows=tuple(rows)),
        cumulative_usage=cumulative_usage,
        closed=trailer is not None,
        path=target,
        trailer_raw=trailer,
    )


def delete_session(session_id: UUID | str, *, path: Path | None = None) -> bool:
    """Remove the on-disk JSONL file for ``session_id``.

    Returns ``True`` when the file existed and was removed, ``False`` when
    it was already absent. Does not touch any associated sandbox dir — pair
    with :meth:`PersistentSandboxRegistry.delete_local` when removing the
    sandbox is also desired.
    """
    target = (path or session_file(session_id)).resolve()
    removed = False
    if target.is_file():
        target.unlink()
        removed = True
    if path is None:
        partial = session_partial_file(session_id).resolve()
        if partial.is_file():
            partial.unlink()
            removed = True
    return removed


def prune_sessions(*, older_than: timedelta) -> list[UUID]:
    """Delete persisted sessions whose ``created_at`` is older than ``older_than``.

    Returns the removed session ids in deletion order. Files that fail to
    parse are skipped (and not pruned — manual cleanup is safer than auto-
    delete in that case).
    """
    cutoff = datetime.now(timezone.utc) - older_than
    removed: list[UUID] = []
    for meta in list_persisted_sessions():
        created = meta.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created < cutoff and delete_session(meta.id, path=meta.path):
            removed.append(meta.id)
    return removed


def list_persisted_sessions() -> list[PersistedSessionMeta]:
    """Enumerate persisted sessions in the resolved sessions directory.

    Sorted by ``created_at`` ascending (oldest first). Files that fail to
    parse are skipped with a logged warning rather than aborting the whole
    listing.
    """
    target_dir = sessions_dir()
    if not target_dir.is_dir():
        return []
    metas: list[PersistedSessionMeta] = []
    for entry in sorted(target_dir.iterdir()):
        if not entry.is_file():
            continue
        name = entry.name
        if not (
            name.endswith(SESSION_FILE_SUFFIX) or name.endswith(SESSION_PARTIAL_SUFFIX)
        ):
            continue
        try:
            metas.append(_meta_from_file(entry))
        except PersistenceError:
            logger.warning(
                "skipping unreadable persisted session %s", entry, exc_info=True
            )
    metas.sort(key=lambda m: m.created_at)
    return metas


# ----------------------------------------------------------------------- internals


def _header_from_record(
    record: dict[str, Any], *, path: Path, lineno: int
) -> PersistedSessionHeader:
    try:
        return PersistedSessionHeader(
            schema_version=int(record.get("schema_version", 0)),
            id=UUID(str(record["id"])),
            created_at=datetime.fromisoformat(str(record["created_at"])),
            parent_session_ids=parse_uuid_list(record.get("parent_session_ids")),
            lineage_operator=str(record.get("lineage_operator", "implicit")),
            lineage_kind=coerce_lineage_kind(record.get("lineage_kind")),
            lineage_extras=lineage_extras_from_jsonable(record.get("lineage_extras")),
            sandbox_backend=record.get("sandbox_backend"),
            sandbox_spec=spec_from_jsonable(record.get("sandbox_spec")),
            sandbox_handle_id=record.get("sandbox_handle_id"),
        )
    except (KeyError, ValueError, TypeError) as e:
        raise PersistenceError(
            f"{path}:{lineno}: malformed header record: {e}",
        ) from e


def _chunk_from_record(record: dict[str, Any], *, path: Path, lineno: int) -> ChunkRow:
    try:
        kind = ChunkKind(record["kind"])
    except (KeyError, ValueError) as e:
        raise PersistenceError(
            f"{path}:{lineno}: invalid chunk kind: {e}",
        ) from e
    payload = record.get("payload")
    if not isinstance(payload, dict):
        raise PersistenceError(
            f"{path}:{lineno}: chunk payload must be a JSON object",
        )
    return ChunkRow(kind=kind, payload=dict(payload))


def _meta_from_file(path: Path) -> PersistedSessionMeta:
    header: PersistedSessionHeader | None = None
    chunk_count = 0
    closed = False
    try:
        with path.open("r", encoding="utf-8") as fp:
            for lineno, raw_line in enumerate(fp, start=1):
                if not raw_line.endswith("\n"):
                    continue
                line = raw_line.rstrip("\n").strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as e:
                    raise PersistenceError(
                        f"{path}:{lineno}: invalid JSON: {e.msg}",
                    ) from e
                rt = record.get("record_type")
                if rt == "header" and header is None:
                    try:
                        record = upgrade_header(record)
                    except ValueError as e:
                        raise PersistenceError(f"{path}:{lineno}: {e}") from e
                    header = _header_from_record(record, path=path, lineno=lineno)
                elif rt == "chunk":
                    chunk_count += 1
                elif rt == "trailer":
                    closed = True
    except OSError as e:
        raise PersistenceError(f"failed to read {path}: {e}") from e
    if header is None:
        raise PersistenceError(f"{path}: no header record found")
    return PersistedSessionMeta(
        id=header.id,
        path=path,
        created_at=header.created_at,
        lineage_operator=header.lineage_operator,
        lineage_kind=header.lineage_kind,
        chunk_count=chunk_count,
        closed=closed,
    )


def _extract_system_prompt(table: ChunkTable) -> str | None:
    for row in table.rows:
        if row.kind == ChunkKind.SYSTEM:
            content = row.payload.get("content")
            return str(content) if content is not None else None
    return None
