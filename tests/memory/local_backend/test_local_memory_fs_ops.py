"""FS-op tests for :class:`LocalMemoryBackend` — Write / Read / List / Tree.

Real filesystem; no mocks. URI scheme: ``viking://{scope}/...`` where scope
is one of ``user`` / ``agent`` / ``session`` / ``resources``.
"""

from __future__ import annotations

from pathlib import Path

from rath.memory import MemoryStore
from rath.memory.adapters.local import LocalMemoryBackend
from rath.memory.op_types import (
    MemoryOpList,
    MemoryOpRead,
    MemoryOpTree,
    MemoryOpWrite,
)
from rath.memory.results import (
    MemoryExecutionFailure,
    MemoryListResult,
    MemoryReadResult,
    MemoryWriteResult,
)

# ---------------------------------------------------------------- Write


def test_write_creates_md_file_under_scope(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    op = MemoryOpWrite(
        uri="viking://user/memories/preferences/dark_mode",
        content="The user prefers dark mode at night.",
    )
    res = backend.dispatch(store, op)
    assert isinstance(res, MemoryWriteResult)
    assert res.uri == op.uri
    assert res.bytes_written == len(op.content.encode("utf-8"))

    expected = Path(store.handle) / "user" / "memories" / "preferences" / "dark_mode.md"
    assert expected.is_file()
    assert expected.read_text(encoding="utf-8") == op.content


def test_write_overwrites_existing_content(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    uri = "viking://user/memories/preferences/lang"
    backend.dispatch(store, MemoryOpWrite(uri=uri, content="zh"))
    backend.dispatch(store, MemoryOpWrite(uri=uri, content="en"))
    body = Path(store.handle) / "user" / "memories" / "preferences" / "lang.md"
    assert body.read_text(encoding="utf-8") == "en"


def test_write_rejects_unknown_scope(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    op = MemoryOpWrite(uri="viking://bogus/x", content="hi")
    res = backend.dispatch(store, op)
    assert isinstance(res, MemoryExecutionFailure)
    assert res.kind == "invalid_uri"


def test_write_rejects_non_viking_scheme(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    op = MemoryOpWrite(uri="file:///etc/passwd", content="x")
    res = backend.dispatch(store, op)
    assert isinstance(res, MemoryExecutionFailure)
    assert res.kind == "invalid_uri"


def test_write_rejects_parent_traversal(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    op = MemoryOpWrite(uri="viking://user/../../etc/passwd", content="x")
    res = backend.dispatch(store, op)
    assert isinstance(res, MemoryExecutionFailure)
    assert res.kind == "invalid_uri"


# ---------------------------------------------------------------- Read


def test_read_returns_written_content(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    uri = "viking://user/memories/preferences/theme"
    backend.dispatch(store, MemoryOpWrite(uri=uri, content="dark"))
    res = backend.dispatch(store, MemoryOpRead(uri=uri))
    assert isinstance(res, MemoryReadResult)
    assert res.uri == uri
    assert res.data == "dark"
    assert res.level == "detail"


def test_read_missing_uri_returns_not_found(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    res = backend.dispatch(store, MemoryOpRead(uri="viking://user/missing"))
    assert isinstance(res, MemoryExecutionFailure)
    assert res.kind == "not_found"


def test_read_with_no_encoding_returns_bytes(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    uri = "viking://user/memories/raw"
    backend.dispatch(store, MemoryOpWrite(uri=uri, content="ohi"))
    res = backend.dispatch(store, MemoryOpRead(uri=uri, encoding=None))
    assert isinstance(res, MemoryReadResult)
    assert res.data == b"ohi"


def test_read_abstract_level_returns_same_data_in_v1(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    """Local has no abstract/overview/detail hierarchy; every level reads full body."""
    uri = "viking://user/memories/preferences/note"
    backend.dispatch(store, MemoryOpWrite(uri=uri, content="full body"))
    abstract = backend.dispatch(store, MemoryOpRead(uri=uri, level="abstract"))
    assert isinstance(abstract, MemoryReadResult)
    assert abstract.data == "full body"
    assert abstract.level == "abstract"


# ---------------------------------------------------------------- List


def test_list_returns_immediate_children_only(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    backend.dispatch(
        store, MemoryOpWrite(uri="viking://user/memories/preferences/a", content="1")
    )
    backend.dispatch(
        store, MemoryOpWrite(uri="viking://user/memories/preferences/b", content="2")
    )
    backend.dispatch(
        store, MemoryOpWrite(uri="viking://user/memories/notes/c", content="3")
    )

    res = backend.dispatch(
        store, MemoryOpList(uri="viking://user/memories/preferences")
    )
    assert isinstance(res, MemoryListResult)
    names = {e.name for e in res.entries}
    # Sidecars (.vec) must not surface; .md gets its suffix stripped.
    assert names == {"a", "b"}


def test_list_shows_dirs_and_files_correctly(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    backend.dispatch(
        store, MemoryOpWrite(uri="viking://user/memories/notes/x", content="x")
    )
    backend.dispatch(
        store, MemoryOpWrite(uri="viking://user/memories/preferences/y", content="y")
    )
    res = backend.dispatch(store, MemoryOpList(uri="viking://user/memories"))
    assert isinstance(res, MemoryListResult)
    by_name = {e.name: e for e in res.entries}
    assert set(by_name) == {"notes", "preferences"}
    assert by_name["notes"].is_dir is True


def test_list_empty_uri_returns_empty(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    res = backend.dispatch(store, MemoryOpList(uri="viking://user"))
    assert isinstance(res, MemoryListResult)
    assert res.entries == ()


def test_list_invalid_scope_is_invalid_uri(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    res = backend.dispatch(store, MemoryOpList(uri="viking://bogus"))
    assert isinstance(res, MemoryExecutionFailure)
    assert res.kind == "invalid_uri"


# ---------------------------------------------------------------- Tree


def test_tree_walks_recursively_up_to_depth(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    backend.dispatch(
        store, MemoryOpWrite(uri="viking://user/memories/preferences/a", content="1")
    )
    backend.dispatch(
        store, MemoryOpWrite(uri="viking://user/memories/notes/b", content="2")
    )
    res = backend.dispatch(store, MemoryOpTree(uri="viking://user", depth=4))
    assert isinstance(res, MemoryListResult)
    uris = {e.uri for e in res.entries}
    # Expect at least the two leaves and their parent dirs.
    assert "viking://user/memories/preferences/a" in uris
    assert "viking://user/memories/notes/b" in uris


def test_tree_depth_zero_is_just_root(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    backend.dispatch(
        store, MemoryOpWrite(uri="viking://user/memories/preferences/a", content="1")
    )
    res = backend.dispatch(store, MemoryOpTree(uri="viking://user", depth=0))
    assert isinstance(res, MemoryListResult)
    # depth=0 → only the directories *at* viking://user (one level), no leaves.
    for e in res.entries:
        # Each entry must be a direct child of viking://user (one extra slash).
        tail = e.uri.removeprefix("viking://user/")
        assert "/" not in tail


def test_tree_drops_vec_sidecars(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    backend.dispatch(
        store, MemoryOpWrite(uri="viking://user/memories/notes/a", content="hello")
    )
    # Drop a fake .vec file next to a.md.
    vec = Path(store.handle) / "user" / "memories" / "notes" / "a.vec"
    vec.write_bytes(b"\x00" * 8)
    res = backend.dispatch(store, MemoryOpTree(uri="viking://user/memories", depth=4))
    assert isinstance(res, MemoryListResult)
    assert all(not e.uri.endswith(".vec") for e in res.entries)
    assert all(not e.name.endswith(".vec") for e in res.entries)
