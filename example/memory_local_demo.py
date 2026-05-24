"""Example: ``LocalMemoryBackend`` — the zero-dependency memory backend.

This demo runs out of the box with ``pip install openrath`` — no Docker,
no OpenViking, no extras. It exercises four code paths:

1. :class:`MemoryOpWrite` stores a freeform memory file under
   ``viking://user/memories/...``.
2. :class:`MemoryOpFind` searches via BM25 (lexical) or, if
   ``OPENAI_API_KEY`` is set, cached embedding rank.
3. :class:`MemoryOpResource` ingests a local file under
   ``viking://resources/<sha>/``.
4. :class:`MemoryOpCommit` archives a tiny session under
   ``viking://session/<sid>/commits/<utc-stamp>/``.

No ``assert`` — the demo prints ``[ok]`` / ``[note]`` markers so a human
can eyeball the output.
"""

from __future__ import annotations

import os
import tempfile

import rath.memory as memory
from rath.memory.abc import MemoryStoreSpec
from rath.memory.op_types import (
    MemoryOpCommit,
    MemoryOpFind,
    MemoryOpResource,
    MemoryOpWrite,
)


def _maybe_embedding_client() -> object | None:
    """Build a live embedding client if ``OPENAI_API_KEY`` is exported."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from rath.llm.embedding import (
            EmbeddingProvider,
            RathOpenAIEmbeddingClient,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[note] embedding extras not installed: {exc}")
        return None
    provider = EmbeddingProvider(
        api_key=api_key,
        base_url=os.environ.get("OPENAI_BASE_URL") or None,
        model=os.environ.get("OPENAI_EMBEDDING_MODEL") or "embedding-3",
    )
    return RathOpenAIEmbeddingClient(provider)


def main() -> None:
    backend = memory.current()
    print(f"[ok] default memory backend: {backend.name}")

    options: dict = {}
    embed_client = _maybe_embedding_client()
    if embed_client is not None:
        options["embedding"] = embed_client
        print("[ok] embedding-rank Find enabled (OPENAI_API_KEY set)")
    else:
        print("[note] no OPENAI_API_KEY — Find will use BM25 lexical fallback")

    store = backend.open(MemoryStoreSpec(options=options))
    try:
        print(f"[ok] opened local store at {store.handle}")

        # 1) remember
        backend.dispatch(
            store,
            MemoryOpWrite(
                uri="viking://user/memories/preferences/dark_mode",
                content="The user prefers a dark colour theme at night.",
            ),
        )
        backend.dispatch(
            store,
            MemoryOpWrite(
                uri="viking://user/memories/preferences/language",
                content="The user reads English and writes Python.",
            ),
        )
        print("[ok] wrote two preference memos")

        # 2) recall
        hits = backend.dispatch(
            store,
            MemoryOpFind(query="reading code at night", top_k=3),
        )
        print(f"[ok] Find returned {len(hits.hits)} hit(s)")
        for hit in hits.hits:
            print(f"      {hit.score:6.3f}  {hit.uri}")

        # 3) resource ingest from a tmp file
        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        ) as tf:
            tf.write("Some external knowledge worth keeping.")
            tmp_path = tf.name
        res = backend.dispatch(store, MemoryOpResource(source=tmp_path))
        print(f"[ok] resource ingested at {res.uri}")

        # 4) commit a tiny session (archive only — wait=False, no extraction)
        commit_res = backend.dispatch(
            store,
            MemoryOpCommit(
                session_id="demo-session",
                messages=[
                    {"role": "user", "content": "remember: I like dark mode"},
                    {"role": "assistant", "content": "got it."},
                ],
                wait=False,
            ),
        )
        print(f"[ok] commit archived at {commit_res.archived_uri}")
    finally:
        if not store.closed:
            backend.close(store)
        print("[ok] store closed (data persists on disk for next run)")


if __name__ == "__main__":
    main()
