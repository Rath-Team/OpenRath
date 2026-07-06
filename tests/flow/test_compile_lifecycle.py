"""P5.5 — CompiledWorkflow lifecycle context manager.

`with wf.compile() as cw:` pre-acquires the planned resources (memory stores
bound on reachable AgentParams) and releases them in reverse order on exit,
even on exception. Refcounts return to baseline. Real local memory backend
(no mocks).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from rath.flow.agent_param import AgentParam
from rath.flow.workflow import Workflow
from rath.llm.provider import Provider
from rath.memory import get as get_memory_backend
from rath.session.session import Session


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("OPENRATH_HOME", str(tmp_path / "home"))
    yield


def _local_store():  # type: ignore[no-untyped-def]
    return get_memory_backend("local").open()


class _MemWF(Workflow):
    def __init__(self, store) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.a = AgentParam(
            Session.from_agent_prompt("s"),
            Provider(model="m", api_key="sk"),
            memory=store,
        )

    def forward(self, session: Session) -> Session:
        return session


def test_context_manager_acquires_and_releases() -> None:
    store = _local_store()
    baseline = store.refcount
    wf = _MemWF(store)
    with wf.compile() as cw:
        # inside the block the planned memory store has an extra reference
        assert store.refcount == baseline + 1
        assert cw.workflow is wf
    # released on exit, back to baseline
    assert store.refcount == baseline


def test_context_manager_releases_on_exception() -> None:
    store = _local_store()
    baseline = store.refcount
    wf = _MemWF(store)
    with pytest.raises(RuntimeError):
        with wf.compile():
            assert store.refcount == baseline + 1
            raise RuntimeError("boom")
    assert store.refcount == baseline


def test_context_manager_no_memory_is_noop() -> None:
    class _Plain(Workflow):
        def __init__(self) -> None:
            super().__init__()
            self.a = AgentParam(Session.from_agent_prompt("s"), Provider(model="m"))

        def forward(self, session: Session) -> Session:
            return session

    wf = _Plain()
    with wf.compile() as cw:
        assert cw.workflow is wf  # no resources to acquire, no error
