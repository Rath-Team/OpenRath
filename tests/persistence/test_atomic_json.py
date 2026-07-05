"""P3.1 — shared atomic-JSON write primitive.

Real filesystem tests only (no mocks). Verifies:
- atomicity: a mid-write failure never leaves a half-written target;
- 0600 perms on POSIX;
- no temp debris on success or failure;
- concurrent writers to the same path from *different* threads do not raise
  (this is the Windows ``os.replace`` PermissionError bug the primitive fixes)
  and the final file is one complete, parseable payload.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

from rath.persistence.atomic import atomic_write_json, atomic_write_text


def test_atomic_write_text_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "a.txt"  # parent does not exist yet
    atomic_write_text(target, "hello\n")
    assert target.read_text(encoding="utf-8") == "hello\n"


def test_atomic_write_json_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "cfg.json"
    payload = {"b": 2, "a": 1, "nested": {"x": [1, 2, 3]}}
    atomic_write_json(target, payload)
    assert json.loads(target.read_text(encoding="utf-8")) == payload


def test_no_partial_file_on_serialization_failure(tmp_path: Path) -> None:
    target = tmp_path / "cfg.json"
    atomic_write_json(target, {"ok": 1})
    original = target.read_text(encoding="utf-8")

    class Unserializable:
        pass

    with pytest.raises(TypeError):
        atomic_write_json(target, {"bad": Unserializable()})

    # Original file untouched; no temp debris.
    assert target.read_text(encoding="utf-8") == original
    assert sorted(p.name for p in tmp_path.glob("*.tmp")) == []
    assert sorted(p.name for p in tmp_path.glob(".*tmp*")) == []


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX perms only")
def test_atomic_write_sets_0600(tmp_path: Path) -> None:
    target = tmp_path / "secret.json"
    atomic_write_json(target, {"k": "v"}, mode=0o600)
    assert (target.stat().st_mode & 0o777) == 0o600


def test_concurrent_writes_same_path_no_error(tmp_path: Path) -> None:
    """5 threads write the same path simultaneously via independent calls.

    Must not raise (the primitive serializes replace via a path-keyed lock
    and retries the Windows sharing-violation window), and the final file
    must be exactly one writer's complete payload.
    """
    target = tmp_path / "shared.json"
    barrier = threading.Barrier(5)
    errors: list[BaseException] = []

    def _writer(tag: int) -> None:
        try:
            barrier.wait(timeout=5.0)
            atomic_write_json(target, {"writer": tag, "pad": "x" * (tag + 1)})
        except BaseException as exc:  # noqa: BLE001 -- collected for assertion
            errors.append(exc)

    threads = [threading.Thread(target=_writer, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)
        assert not t.is_alive()

    assert not errors, f"concurrent atomic writes raised: {errors!r}"
    final = json.loads(target.read_text(encoding="utf-8"))
    assert final["writer"] in set(range(5))
    # No temp debris from any writer.
    leftovers = sorted(p.name for p in tmp_path.iterdir() if p.name != "shared.json")
    assert leftovers == [], f"atomic write left debris: {leftovers}"


def test_write_text_trailing_newline_option(tmp_path: Path) -> None:
    target = tmp_path / "n.txt"
    atomic_write_text(target, "line", newline=False)
    assert target.read_text(encoding="utf-8") == "line"
    atomic_write_text(target, "line", newline=True)
    assert target.read_text(encoding="utf-8") == "line\n"
