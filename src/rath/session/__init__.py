"""Session package: chunks, sandbox loop, registry, lineage graph, and primitives."""

from rath.session.chunk import (
    ChunkKind,
    ChunkRow,
    ChunkTable,
    assistant_turn_chunk,
    chunk_table_to_messages,
    format_chunk_row_brief,
    system_text_chunk,
    tool_feedback_chunk,
    user_text_chunk,
)
from rath.session.compress import run_session_compress
from rath.session.graph import (
    LineageConsistencyError,
    LineageJournal,
    LineageKind,
    LineageRecorder,
    SessionLineage,
    ancestors_bfs,
    descendants_dfs_preorder,
    edge_pairs,
    lineage_journal_optional,
    lineage_journal_tracking,
    lineage_view_dataclass,
    session_graph_mode,
    session_graph_mode_override,
    validate_acyclic,
)
from rath.session.loop import (
    SessionLoopExecutor,
    run_session_loop,
)
from rath.session.manager import SessionRegistry, session_registry
from rath.session.persistence import (
    PersistedSession,
    PersistedSessionHeader,
    PersistedSessionMeta,
    PersistenceError,
    SessionWriter,
    delete_session,
    list_persisted_sessions,
    load_session,
    prune_sessions,
)
from rath.session.primitives import (
    create_system_session,
    create_user_session,
    detach_session,
    fork_session,
)
from rath.session.provider_builtin import DefaultSessionLoopExecutor
from rath.session.select import select_session
from rath.session.session import Session

__all__ = [
    "ancestors_bfs",
    "assistant_turn_chunk",
    "chunk_table_to_messages",
    "ChunkKind",
    "ChunkRow",
    "ChunkTable",
    "create_system_session",
    "create_user_session",
    "DefaultSessionLoopExecutor",
    "descendants_dfs_preorder",
    "detach_session",
    "edge_pairs",
    "fork_session",
    "format_chunk_row_brief",
    "LineageConsistencyError",
    "LineageJournal",
    "lineage_journal_optional",
    "lineage_journal_tracking",
    "LineageKind",
    "LineageRecorder",
    "lineage_view_dataclass",
    "session_graph_mode",
    "session_graph_mode_override",
    "Session",
    "SessionLineage",
    "SessionLoopExecutor",
    "SessionRegistry",
    "run_session_compress",
    "run_session_loop",
    "select_session",
    "session_registry",
    "system_text_chunk",
    "tool_feedback_chunk",
    "user_text_chunk",
    "validate_acyclic",
    # Persistence (append-only JSONL per session, see rath.session.persistence)
    "PersistedSession",
    "PersistedSessionHeader",
    "PersistedSessionMeta",
    "PersistenceError",
    "SessionWriter",
    "delete_session",
    "list_persisted_sessions",
    "load_session",
    "prune_sessions",
]
