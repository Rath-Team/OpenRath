from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from rath.persistence import dumps_jsonl, iter_jsonl, write_jsonl


def test_dumps_jsonl_is_strict_and_preserves_insertion_order() -> None:
    text = dumps_jsonl([{"z": "中文", "a": 1}, {"second": True}])
    assert text == '{"z": "中文", "a": 1}\n{"second": true}\n'
    with pytest.raises(ValueError):
        dumps_jsonl([{"bad": float("nan")}])
    with pytest.raises(ValueError):
        dumps_jsonl([{"bad": float("inf")}])
    with pytest.raises(TypeError):
        dumps_jsonl([{"bad": object()}])


def test_overwrite_serializes_before_touching_target(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text('{"old": true}\n', encoding="utf-8")
    with pytest.raises(TypeError):
        write_jsonl(path, [{"bad": object()}])
    assert path.read_text(encoding="utf-8") == '{"old": true}\n'
    assert not list(tmp_path.glob(".atomic_*"))


def test_overwrite_write_failure_keeps_previous_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text('{"old": true}\n', encoding="utf-8")

    def _fail(*args: Any, **kwargs: Any) -> None:
        raise OSError("disk error")

    monkeypatch.setattr("rath.persistence.jsonl.atomic_write_text", _fail)
    with pytest.raises(OSError, match="disk error"):
        write_jsonl(path, [{"new": True}])
    assert path.read_text(encoding="utf-8") == '{"old": true}\n'


def test_append_never_truncates_and_concurrent_batches_are_parseable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "records.jsonl"
    write_jsonl(path, [{"seed": 1}])

    def _append(worker: int) -> None:
        write_jsonl(
            path,
            ({"worker": worker, "index": i} for i in range(25)),
            append=True,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_append, range(4)))
    rows = [record for _, record in iter_jsonl(path)]
    assert rows[0] == {"seed": 1}
    assert len(rows) == 101
    assert {(row["worker"], row["index"]) for row in rows[1:]} == {
        (worker, index) for worker in range(4) for index in range(25)
    }


def test_append_lock_failure_is_surfaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "records.jsonl"

    def _fail(self: Any) -> None:
        raise RuntimeError("lock failed")

    monkeypatch.setattr("rath.persistence.jsonl.FileLock.acquire", _fail)
    with pytest.raises(RuntimeError, match="lock failed"):
        write_jsonl(path, [{"row": 1}], append=True)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ('{"ok": 1}\nnot-json\n', "records.jsonl:2"),
        ("[1, 2, 3]\n", "records.jsonl:1"),
    ],
)
def test_reader_diagnostics_include_path_and_line(
    tmp_path: Path, body: str, message: str
) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(ValueError, match=message.replace(".", r"\.")):
        list(iter_jsonl(path))


def test_reader_skips_empty_lines(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text('\n{"a": 1}\n   \n{"b": 2}\n', encoding="utf-8")
    assert list(iter_jsonl(path)) == [(2, {"a": 1}), (4, {"b": 2})]
