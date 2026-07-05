"""P3.2 — backend remote-sandbox registry writes are atomic (no bare write_text).

Real filesystem. Verifies record_remote / touch_remote leave a complete,
parseable file and no ``.atomic_*.tmp`` debris, and that concurrent record
calls to the same id do not raise on Windows (the atomic primitive serializes
+ retries the replace).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from uuid import uuid4

from rath.backend.persistence.registry import PersistentSandboxRegistry


def test_record_remote_is_atomic_and_clean(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    sid = reg.record_remote("opensandbox", "native-123")
    rec = reg.load_remote(sid)
    assert rec is not None and rec.remote_id == "native-123"

    # File is complete JSON, no temp debris in the opensandbox dir.
    from rath.backend.persistence.paths import opensandbox_index_path

    path = opensandbox_index_path(sid)
    json.loads(path.read_text(encoding="utf-8"))  # parses
    debris = [p.name for p in path.parent.glob(".atomic_*")]
    assert debris == []


def test_touch_remote_is_atomic(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    sid = reg.record_remote("opensandbox", "native-xyz")
    before = reg.load_remote(sid)
    assert before is not None
    reg.touch_remote(sid)
    after = reg.load_remote(sid)
    assert after is not None
    assert after.remote_id == "native-xyz"
    # last_used advanced (or at least stayed a valid ISO timestamp).
    assert after.last_used_at is not None


def test_registry_uses_atomic_primitive_not_bare_write_text() -> None:
    """Guard: the registry persists JSON via the atomic primitive, not the
    non-atomic path.write_text (which leaves a truncated file on a crash)."""
    import rath.backend.persistence.registry as reg_mod

    src = Path(reg_mod.__file__).read_text(encoding="utf-8")
    assert "atomic_write_json" in src, "registry should use atomic_write_json"
    assert ".write_text(" not in src, "registry should not use bare write_text"


def test_concurrent_record_same_id_no_error(_isolate_openrath_home: Path) -> None:
    reg = PersistentSandboxRegistry()
    fixed = uuid4()
    barrier = threading.Barrier(5)
    errors: list[BaseException] = []

    def _w(tag: int) -> None:
        try:
            barrier.wait(timeout=5.0)
            reg.record_remote("opensandbox", f"native-{tag}", sandbox_id=fixed)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_w, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)
    assert not errors, f"concurrent record_remote raised: {errors!r}"
    rec = reg.load_remote(fixed)
    assert rec is not None and rec.remote_id.startswith("native-")
