"""Commit tests for :class:`LocalMemoryBackend`.

Real filesystem; the extraction path uses the live GLM chat client gated
on ``OPENAI_API_KEY`` (the project ships a key in ``config.json``). No
mocks, no in-process doubles.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from rath.llm.openai.client import RathOpenAIChatClient
from rath.llm.provider import Provider
from rath.memory import MemoryStore, MemoryStoreSpec
from rath.memory.adapters.local import LocalMemoryBackend
from rath.memory.op_types import MemoryOpCommit, MemoryOpList, MemoryOpRead
from rath.memory.results import (
    MemoryCommitResult,
    MemoryListResult,
    MemoryReadResult,
)

_HAS_LIVE_KEY = len(os.environ.get("OPENAI_API_KEY", "").strip()) >= 8
_live_only = pytest.mark.skipif(
    not _HAS_LIVE_KEY,
    reason="OPENAI_API_KEY not set (live commit-extraction tests)",
)


@pytest.fixture
def live_chat_client() -> RathOpenAIChatClient:
    api_key = os.environ["OPENAI_API_KEY"].strip()
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    model = os.environ.get("OPENAI_CHAT_MODEL", "").strip() or "glm-4.6"
    provider = Provider(
        provider_kind="openai",
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0.0,
    )
    return RathOpenAIChatClient(provider)


@pytest.fixture
def chat_store(
    backend: LocalMemoryBackend,
    live_chat_client: RathOpenAIChatClient,
) -> Iterator[MemoryStore]:
    spec = MemoryStoreSpec(options={"chat": live_chat_client})
    s = backend.open(spec)
    try:
        yield s
    finally:
        if not s.closed:
            backend.close(s)


# ----------------------------------------------------- Archive (no extraction)


def test_commit_writes_messages_archive_under_session(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    res = backend.dispatch(
        store,
        MemoryOpCommit(session_id="s-001", messages=msgs, wait=False),
    )
    assert isinstance(res, MemoryCommitResult)
    assert res.archived_uri is not None
    assert res.archived_uri.startswith("viking://session/s-001/commits/")
    assert res.archived_uri.endswith("/messages.json")
    # extracted_count=-1 when no extraction was attempted.
    assert res.extracted_count == -1

    read = backend.dispatch(store, MemoryOpRead(uri=res.archived_uri, encoding="utf-8"))
    assert isinstance(read, MemoryReadResult)
    payload = json.loads(read.data)
    assert payload == msgs


def test_commit_archives_each_call_into_its_own_dir(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    backend.dispatch(
        store,
        MemoryOpCommit(
            session_id="s-002",
            messages=[{"role": "user", "content": "a"}],
            wait=False,
        ),
    )
    backend.dispatch(
        store,
        MemoryOpCommit(
            session_id="s-002",
            messages=[{"role": "user", "content": "b"}],
            wait=False,
        ),
    )
    commits_dir = Path(store.handle) / "session" / "s-002" / "commits"
    children = sorted(p.name for p in commits_dir.iterdir() if p.is_dir())
    assert len(children) == 2, children


def test_commit_with_no_chat_client_skips_extraction(
    backend: LocalMemoryBackend, store: MemoryStore
) -> None:
    res = backend.dispatch(
        store,
        MemoryOpCommit(
            session_id="s-003",
            messages=[{"role": "user", "content": "x"}],
            wait=True,
        ),
    )
    assert isinstance(res, MemoryCommitResult)
    # wait=True but no chat client → still archive, just no extraction.
    assert res.extracted_count == 0
    extracted_dir = Path(store.handle) / "user" / "memories" / "extracted"
    assert not extracted_dir.exists()


# ----------------------------------------------------- Extraction (wait=True + live chat)


@_live_only
@pytest.mark.live_llm
def test_commit_wait_with_chat_extracts_memos(
    backend: LocalMemoryBackend, chat_store: MemoryStore
) -> None:
    res = backend.dispatch(
        chat_store,
        MemoryOpCommit(
            session_id="s-004",
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Two facts about me to remember: "
                        "I prefer a dark colour theme, "
                        "and I write Python for my day job."
                    ),
                },
            ],
            wait=True,
            timeout_seconds=60.0,
        ),
    )
    assert isinstance(res, MemoryCommitResult)
    # The model should produce >=1 memo from two clear facts.
    assert res.extracted_count >= 1

    listing = backend.dispatch(
        chat_store,
        MemoryOpList(uri="viking://user/memories/extracted"),
    )
    assert isinstance(listing, MemoryListResult)
    assert len(listing.entries) == res.extracted_count


@_live_only
@pytest.mark.live_llm
def test_commit_async_wait_false_does_not_run_extraction(
    backend: LocalMemoryBackend, chat_store: MemoryStore
) -> None:
    res = backend.dispatch(
        chat_store,
        MemoryOpCommit(
            session_id="s-005",
            messages=[{"role": "user", "content": "hi"}],
            wait=False,
        ),
    )
    assert isinstance(res, MemoryCommitResult)
    # wait=False → extraction deferred; v1 local has no background queue, -1.
    assert res.extracted_count == -1
    extracted_dir = Path(chat_store.handle) / "user" / "memories" / "extracted"
    assert not extracted_dir.exists()
