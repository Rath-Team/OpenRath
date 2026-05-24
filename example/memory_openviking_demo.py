"""Example: ``Agent`` bound to an OpenViking memory store.

Run modes:

- **HTTP mode (preferred)**: export ``OPEN_VIKING_URL`` and
  ``OPEN_VIKING_API_KEY`` to point at a running OpenViking server.
  The repo's ``scripts/launch_openviking.sh`` (Linux/macOS) /
  ``scripts/launch_openviking.bat`` (Windows) brings one up locally
  in Docker.
- **Embedded mode (fallback)**: if no URL is set the demo opens an
  embedded store under a tmp dir; this requires the ``pyagfs``
  binding-client wheel to be installed. Skip this demo if neither
  mode is available.

The demo exercises four code paths:

1. ``agent.remember`` writes a freeform memory file;
2. ``agent.recall`` searches for it;
3. ``agent.commit`` archives a tiny scripted session for extraction;
4. ``agent.close`` releases the store reference (also via ``with`` block).

No ``assert`` — the demo prints ``[ok]`` / ``[note]`` markers so a
human can eyeball the output.
"""

from __future__ import annotations

import os
import tempfile

import rath.memory as memory
from rath.flow.agent import Agent
from rath.flow.memory_inject import DefaultRecallInjection
from rath.memory.abc import MemoryStoreSpec
from rath.session import Session


def _build_store_spec() -> tuple[str, MemoryStoreSpec] | None:
    url = os.environ.get("OPEN_VIKING_URL", "").strip()
    api_key = os.environ.get("OPEN_VIKING_API_KEY", "").strip()
    if url and api_key:
        return (
            "http",
            MemoryStoreSpec(
                account_id="default",
                user_id="default",
                agent_id="default",
                options={"url": url, "api_key": api_key},
            ),
        )
    if memory.is_available("openviking"):
        tmp = tempfile.mkdtemp(prefix="openrath_ov_demo_")
        return ("embedded", MemoryStoreSpec(options={"path": tmp}))
    return None


def _build_provider() -> object | None:
    try:
        from _openai_provider import provider_from_env  # type: ignore[import-not-found]

        return provider_from_env()
    except Exception as exc:
        print(f"[note] cannot build LLM provider ({exc}); demo will skip forward()")
        return None


def main() -> None:
    if not memory.is_available("openviking"):
        print(
            "[skip] openviking adapter not installed — run `uv pip install openrath[openviking]`"
        )
        return

    spec_info = _build_store_spec()
    if spec_info is None:
        print(
            "[skip] no OpenViking endpoint available: export OPEN_VIKING_URL/OPEN_VIKING_API_KEY "
            "or install the embedded `pyagfs` wheel"
        )
        return
    mode, spec = spec_info
    print(f"[ok] opening OpenViking store in {mode} mode")

    backend = memory.get("openviking")
    store = backend.open(spec)
    try:
        provider = _build_provider()
        if provider is None:
            print("[note] running memory ops directly on the store")
            from rath.memory.op_types import MemoryOpFind, MemoryOpWrite

            # remember
            uri = "viking://user/memories/preferences/demo"
            try:
                store.dispatch(
                    MemoryOpWrite(uri=uri, content="dark mode preferred", wait=False)
                )
                print(f"[ok] wrote a memory at {uri}")
            except Exception as exc:
                print(
                    f"[note] write failed (likely because the URI does not yet exist): {exc}"
                )
            # recall
            res = store.dispatch(MemoryOpFind(query="dark mode", top_k=3))
            print(f"[ok] recall returned {len(res.hits)} hit(s)")
            return

        with Agent(
            "You are a tidy assistant.",
            provider=provider,
            memory=store,
            memory_inject=DefaultRecallInjection(
                top_k=3, target_uri="viking://user/memories/"
            ),
            commit_on_forward=False,
        ) as agent:
            print("[ok] agent bound to memory store")
            # 1) remember
            try:
                agent.remember(
                    "User prefers dark mode and concise responses.",
                    scope="user",
                    category="preferences",
                )
                print("[ok] remember dispatched")
            except Exception as exc:
                print(f"[note] remember failed: {exc}")
            # 2) recall
            try:
                result = agent.recall("dark mode preferences", top_k=3)
                print(
                    f"[ok] recall returned {len(getattr(result, 'hits', ()) or ())} hit(s)"
                )
            except Exception as exc:
                print(f"[note] recall failed: {exc}")
            # 3) commit a tiny session
            try:
                sess = Session.from_user_message("Remember: I like dark mode.")
                agent.commit(sess, wait=False)
                print("[ok] commit dispatched (extraction is async)")
            except Exception as exc:
                print(f"[note] commit failed: {exc}")
    finally:
        if not store.closed:
            backend.close(store)
        print("[ok] store closed")


if __name__ == "__main__":
    main()
