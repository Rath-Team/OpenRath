"""Tests for ``ConfigStore.load`` caching and ``save`` atomicity.

These cover the perf path (``load()`` may return a cached instance when
the underlying file has not changed) and the safety path (the cache key
must invalidate when content changes even within one filesystem-mtime
tick, which on HFS+ is 1 second).
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Iterator

import pytest

from rath.config.paths import resolve_config_path
from rath.config.schema import LLMProviderConfig
from rath.config.store import ConfigStore


@pytest.fixture(autouse=True)
def _clear_class_cache() -> Iterator[None]:
    """Cache is class-level state — clear before and after every test."""
    ConfigStore._cache.clear()
    yield
    ConfigStore._cache.clear()


def _seed_config_file(home: Path, api_key: str = "sk-initial") -> Path:
    """Write a valid minimal config to the resolved OPENRATH_HOME path."""
    path = resolve_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    store = ConfigStore(path=path)
    store.config.llm.providers["main"] = LLMProviderConfig(
        provider_kind="openai", model="gpt-5", api_key=api_key
    )
    store.config.llm.default_provider = "main"
    store.save()
    # ``save()`` invalidates the cache; reset state so callers begin
    # from a known empty cache too.
    ConfigStore._cache.clear()
    return path


def test_load_returns_cached_instance_when_unchanged(
    _isolate_openrath_home: Path,
) -> None:
    _seed_config_file(_isolate_openrath_home)
    first = ConfigStore.load()
    second = ConfigStore.load()
    assert second is first, (
        "load() must return the same instance when the file hasn't "
        "changed — otherwise the cache isn't doing its job"
    )


def test_save_invalidates_cache_for_next_load(
    _isolate_openrath_home: Path,
) -> None:
    """In-process: after save(), the next load() must reflect the new data."""
    _seed_config_file(_isolate_openrath_home, api_key="sk-v1")
    first = ConfigStore.load()
    assert first.config.llm.providers["main"].api_key == "sk-v1"

    first.config.llm.providers["main"] = LLMProviderConfig(
        provider_kind="openai", model="gpt-5", api_key="sk-v2"
    )
    first.save()

    second = ConfigStore.load()
    assert second.config.llm.providers["main"].api_key == "sk-v2"
    # Cache invalidated → fresh instance returned (not the stale ``first``).
    # NB: this is the contract; we don't assert ``is`` here because the
    # rebuild may legitimately reuse identity in pathological cases.


def test_load_rebuilds_when_file_mtime_changes(
    _isolate_openrath_home: Path,
) -> None:
    """An out-of-band edit (mtime bump) must invalidate the cache."""
    path = _seed_config_file(_isolate_openrath_home, api_key="sk-v1")
    first = ConfigStore.load()

    # Simulate an external editor rewriting the file with new content
    # and a future mtime — bypasses ConfigStore.save() (and therefore
    # the in-process cache invalidation), so the cache must invalidate
    # itself based on the stamp.
    data = json.loads(path.read_text(encoding="utf-8"))
    data["llm"]["providers"]["main"]["api_key"] = "sk-external-edit"
    path.write_text(json.dumps(data), encoding="utf-8")
    # Force a different mtime so the cache key differs even on coarse
    # filesystems.
    future = time.time() + 2.0
    os.utime(path, (future, future))

    second = ConfigStore.load()
    assert second is not first
    assert second.config.llm.providers["main"].api_key == "sk-external-edit"


def test_same_mtime_but_different_size_invalidates_cache(
    _isolate_openrath_home: Path,
) -> None:
    """Regression: on HFS+ (1-second mtime resolution), two writes within
    the same second produce identical ``st_mtime_ns``. A mtime-only cache
    key would return the **previous** content. ``ConfigStore`` keys on
    ``(mtime_ns, size)`` so any rewrite that changes byte count is still
    detected even when mtime ties.
    """
    path = _seed_config_file(_isolate_openrath_home, api_key="sk-short")
    first = ConfigStore.load()
    first_mtime = path.stat().st_mtime_ns

    # Append-style rewrite: same mtime, different size.
    data = json.loads(path.read_text(encoding="utf-8"))
    data["llm"]["providers"]["main"]["api_key"] = (
        "sk-much-longer-second-write-different-byte-count-xxxxxxxxxxxxx"
    )
    path.write_text(json.dumps(data), encoding="utf-8")
    # Force the rewrite's mtime back to the original — simulates HFS+
    # second-level resolution colliding within the same tick.
    atime = path.stat().st_atime_ns
    os.utime(path, ns=(atime, first_mtime))

    assert path.stat().st_mtime_ns == first_mtime, "test setup did not pin mtime"
    assert path.stat().st_size != len(
        json.dumps(json.loads('{"llm":{"providers":{"main":{"api_key":"sk-short"}}}}'))
    ), "rewrite did not actually change byte count"

    second = ConfigStore.load()
    assert second is not first, (
        "size-changed rewrite must invalidate the cache even when mtime ties"
    )
    assert second.config.llm.providers["main"].api_key.startswith("sk-much-longer")


def test_load_when_file_missing_does_not_cache(
    _isolate_openrath_home: Path,
) -> None:
    """If the file doesn't exist, each load() returns a fresh default
    instance (no cache key is meaningful for a non-existent file)."""
    # No seeding — file doesn't exist.
    first = ConfigStore.load()
    second = ConfigStore.load()
    assert first is not second, (
        "non-existent file should not be cached; each load() rebuilds defaults"
    )


def test_concurrent_saves_dont_lose_data_or_leave_tmp(
    _isolate_openrath_home: Path,
) -> None:
    """Atomic-save fix: two threads calling save() simultaneously must
    each end up with a fully-written file (last writer wins) and leave
    no ``.config_*.tmp`` debris in the config dir.
    """
    path = _seed_config_file(_isolate_openrath_home)

    barrier = threading.Barrier(5)
    errors: list[BaseException] = []

    def _writer(tag: str) -> None:
        try:
            store = ConfigStore.load()
            # Mutate to a tag-specific value so we can recognize last-writer
            store.config.llm.providers["main"] = LLMProviderConfig(
                provider_kind="openai", model="gpt-5", api_key=f"sk-{tag}"
            )
            barrier.wait(timeout=5.0)
            store.save()
        except BaseException as exc:  # noqa: BLE001 -- collected for assertion
            errors.append(exc)

    threads = [threading.Thread(target=_writer, args=(str(i),)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)
        assert not t.is_alive()
    assert not errors, f"concurrent save raised: {errors!r}"

    # Final file is parseable and reflects ONE of the writers (last to
    # ``replace()`` wins; we don't assert which).
    final = json.loads(path.read_text(encoding="utf-8"))
    final_key = final["llm"]["providers"]["main"]["api_key"]
    assert final_key in {f"sk-{i}" for i in range(5)}

    # No temp files left behind.
    leftover_tmps = sorted(p.name for p in path.parent.glob(".config_*.tmp"))
    assert leftover_tmps == [], f"atomic save left temp files: {leftover_tmps}"
