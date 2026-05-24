"""Backend lock invariants from 阶段 0 of the async-runtime upgrade.

Two invariants under test:

1. **总则 1** — every ``asyncio.Lock`` an async backend uses must be created
   on the runtime loop thread, *not* eagerly in ``__init__``. If a lock is
   bound to the wrong loop, ``async with lock`` will hang or raise.

2. **总则 2** — ``OpenSandboxBackend._fs_locks[handle]`` is an LRU bounded at
   ``_FS_LOCK_LRU`` entries; eviction must skip entries whose ``locked()``
   is True. Otherwise a future writer for the same path gets a brand-new
   lock and races the original holder, violating mutual exclusion.

These are pure invariants of the lock bookkeeping — they do not need a live
opensandbox-server. We construct ``OpenSandboxBackend`` and probe its
``_exec_lock_for`` / ``_fs_lock_for`` helpers directly on the runtime loop.
"""

from __future__ import annotations

import asyncio

from rath._async.runtime import runtime
from rath.backend.opensandbox import OpenSandboxBackend


def test_exec_lock_is_created_on_runtime_loop() -> None:
    """``_exec_lock_for`` lazy-creates a lock bound to the runtime loop."""
    backend = OpenSandboxBackend()
    rt = runtime()

    async def take_lock_twice() -> bool:
        lock = backend._exec_lock_for("h1")
        async with lock:
            # Re-entry from the same loop is illegal (asyncio.Lock is not
            # reentrant); we just verify acquire/release works once.
            pass
        # Second call must return the same lock object, not a fresh one.
        again = backend._exec_lock_for("h1")
        return again is lock

    assert rt.run(take_lock_twice()) is True


def test_fs_lock_is_created_on_runtime_loop() -> None:
    """``_fs_lock_for`` lazy-creates path locks bound to the runtime loop."""
    backend = OpenSandboxBackend()
    rt = runtime()

    async def acquire_two_paths() -> tuple[bool, bool]:
        a = backend._fs_lock_for("h1", "/workspace/a.txt")
        b = backend._fs_lock_for("h1", "/workspace/b.txt")
        async with a:
            async with b:
                pass
        # Same path → same lock.
        a_again = backend._fs_lock_for("h1", "/workspace/a.txt")
        return (a is a_again, a is not b)

    same, distinct = rt.run(acquire_two_paths())
    assert same is True, "_fs_lock_for must reuse the lock for the same path"
    assert distinct is True, "_fs_lock_for must hand out distinct locks per path"


def test_fs_lock_lru_eviction_skips_held_locks() -> None:
    """LRU eviction must NOT drop a path whose lock is currently held.

    Construction:
      - Fill the LRU to capacity with locks for distinct paths.
      - Hold the first path's lock (simulating an in-flight ``files.write``).
      - Insert one more path → the LRU must evict somebody, but NOT the held lock.
      - Looking the held path up again must return the SAME lock object.
    """
    backend = OpenSandboxBackend()
    cap = OpenSandboxBackend._FS_LOCK_LRU
    rt = runtime()
    handle = "lru-handle"

    async def stress() -> tuple[bool, int]:
        # Fill the table with distinct paths.
        first_path = "/workspace/held.txt"
        first_lock = backend._fs_lock_for(handle, first_path)
        # Hold the first path's lock — this is the "in-flight writer".
        await first_lock.acquire()
        try:
            # Pad up to capacity.
            for i in range(cap - 1):
                backend._fs_lock_for(handle, f"/workspace/pad_{i}.txt")
            # Insert one more path to force eviction.
            backend._fs_lock_for(handle, "/workspace/overflow.txt")
            # The held lock MUST still be in the table and MUST be the same
            # object. If eviction skipped the locked-check, this fails.
            same_after = backend._fs_lock_for(handle, first_path)
            return (same_after is first_lock, len(backend._fs_locks[handle]))
        finally:
            first_lock.release()

    same_lock, table_size = rt.run(stress())
    assert same_lock is True, (
        "LRU eviction violated 总则 2: a held lock was replaced by a fresh one"
    )
    # Table is allowed to be larger than cap when everything else is locked,
    # but the held path is guaranteed to be present.
    assert table_size >= 1


def test_fs_lock_lru_can_evict_unlocked_entries_at_capacity() -> None:
    """When everything is unlocked and we hit capacity, the table is bounded.

    Sanity-check the eviction path itself runs (the previous test only proves
    it *doesn't* evict held locks; we also need to confirm unlocked entries
    are actually dropped, otherwise the "LRU" would be a permanent table).
    """
    backend = OpenSandboxBackend()
    cap = OpenSandboxBackend._FS_LOCK_LRU
    rt = runtime()
    handle = "unlocked-lru"

    async def fill_and_overflow() -> int:
        for i in range(cap + 4):
            backend._fs_lock_for(handle, f"/workspace/file_{i}.txt")
        return len(backend._fs_locks[handle])

    final_size = rt.run(fill_and_overflow())
    # Each overflow insert evicts one unlocked entry → table stays at ``cap``.
    assert final_size == cap, (
        f"expected LRU to stabilise at {cap} entries when all are unlocked, "
        f"got {final_size}"
    )


def test_exec_lock_serialises_concurrent_holders() -> None:
    """Two coroutines contending on the same exec lock observe mutual exclusion."""
    backend = OpenSandboxBackend()
    rt = runtime()
    handle = "exec-serialise"

    async def scenario() -> list[str]:
        lock = backend._exec_lock_for(handle)
        log: list[str] = []

        async def holder(tag: str) -> None:
            async with lock:
                log.append(f"enter-{tag}")
                # Yield to let the other coroutine attempt acquire.
                await asyncio.sleep(0.01)
                log.append(f"exit-{tag}")

        await asyncio.gather(holder("a"), holder("b"))
        return log

    log = rt.run(scenario())
    # Strictly serialised: enter-X / exit-X come before enter-Y / exit-Y.
    assert log[0].startswith("enter-")
    first_tag = log[0].split("-", 1)[1]
    second_tag = "b" if first_tag == "a" else "a"
    assert log == [
        f"enter-{first_tag}",
        f"exit-{first_tag}",
        f"enter-{second_tag}",
        f"exit-{second_tag}",
    ], f"exec lock failed to serialise; observed sequence: {log}"
