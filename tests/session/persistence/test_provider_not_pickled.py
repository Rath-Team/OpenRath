"""P4.6 — a session's bound Provider is never serialized to the JSONL header.

Provider.on_budget_exceeded is a live callable, so a bound provider is not
serializable. Session persistence must not attempt to write it. This locks the
invariant: persisting a session whose provider carries a callback succeeds and
the on-disk header contains no provider / no callback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest

from rath.llm.provider import Provider
from rath.session.persistence._serialize import build_header
from rath.session.session import Session


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("OPENRATH_HOME", str(tmp_path / "home"))
    yield


def _budget_cb(*_a: object, **_k: object) -> None:  # pragma: no cover - never called
    raise AssertionError("should not be invoked")


def test_header_excludes_provider() -> None:
    s = Session.from_user_message("hi").to(
        Provider(model="m", api_key="sk", on_budget_exceeded=_budget_cb)
    )
    header = build_header(s, sandbox_handle_id=None)
    # Header is JSON-serializable (no live callable leaked in).
    dumped = json.dumps(header)
    assert "provider" not in header
    assert "on_budget_exceeded" not in dumped
    assert "_budget_cb" not in dumped


def test_persisted_session_roundtrip_ignores_provider(tmp_path: Path) -> None:
    from rath.session.persistence.writer import SessionWriter

    s = Session.from_user_message("hello").to(
        Provider(model="m", api_key="sk", on_budget_exceeded=_budget_cb)
    )
    out = tmp_path / f"{s.id}.jsonl"
    writer = SessionWriter(s, path=out)
    for i, row in enumerate(s.chunk_table.rows):
        writer.write_chunk(i, row)
    writer.close()

    text = out.read_text(encoding="utf-8")
    assert "on_budget_exceeded" not in text
    assert "_budget_cb" not in text
