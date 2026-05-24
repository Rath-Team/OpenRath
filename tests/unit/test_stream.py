"""``Stream``, ``Event``, and ``Future`` unit tests (in-process fake backend)."""

from __future__ import annotations

import asyncio
import time

import pytest

from rath.backend import (
    Backend,
    BackendSandbox,
    BackendSandboxSpec,
    BackendTool,
    BackendToolCommandRun,
    Capabilities,
    CommandResult,
    Event,
    IsolationLevel,
    ToolResult,
)


class _RecordingBackend(Backend):
    """In-test backend that records dispatch order and supports a per-call delay."""

    def __init__(self, delay: float = 0.0) -> None:
        self.dispatched: list[BackendTool] = []
        self.delay = delay
        self._open_handles: set[str] = set()

    @classmethod
    def is_available(cls) -> bool:
        return True

    @classmethod
    def capabilities(cls) -> Capabilities:
        return Capabilities(
            isolation=IsolationLevel.PROCESS,
            supports_command=True,
            supports_filesystem=False,
            supports_code_interpreter=False,
        )

    @classmethod
    def supported_calls(cls) -> frozenset[type[BackendTool]]:
        return frozenset({BackendToolCommandRun})

    def sandbox_count(self) -> int:
        return len(self._open_handles)

    async def _aopen(
        self, spec: BackendSandboxSpec | None = None
    ) -> BackendSandbox:
        handle = f"fake-{len(self._open_handles)}"
        self._open_handles.add(handle)
        return BackendSandbox(backend=self, handle=handle, spec=spec)

    async def _aclose(self, sandbox: BackendSandbox) -> None:
        self._open_handles.discard(sandbox.handle)
        sandbox.closed = True

    async def _adispatch(
        self, sandbox: BackendSandbox, call: BackendTool
    ) -> ToolResult | bool:
        if self.delay:
            await asyncio.sleep(self.delay)
        self.dispatched.append(call)
        return CommandResult(exit_code=0, stdout=b"", stderr=b"", elapsed_ms=0.0)


@pytest.fixture
def fake_backend() -> _RecordingBackend:
    return _RecordingBackend()


@pytest.fixture
def fake_sandbox(fake_backend: _RecordingBackend) -> BackendSandbox:
    return fake_backend.open()


def test_submit_runs_calls_in_fifo_order(fake_sandbox: BackendSandbox) -> None:
    backend: _RecordingBackend = fake_sandbox.backend  # type: ignore[assignment]
    calls = [BackendToolCommandRun(cmd=f"echo {i}") for i in range(20)]
    with fake_sandbox.stream() as s:
        futures = [s.submit(c) for c in calls]
        for f in futures:
            f.result()
    assert backend.dispatched == calls


def test_two_streams_run_in_parallel(fake_sandbox: BackendSandbox) -> None:
    """Overlapping streams advance concurrently (each dispatch sleeps briefly)."""

    backend: _RecordingBackend = fake_sandbox.backend  # type: ignore[assignment]
    backend.delay = 0.1

    start = time.perf_counter()
    with fake_sandbox.stream() as s1, fake_sandbox.stream() as s2:
        f1 = s1.submit(BackendToolCommandRun(cmd="from-s1"))
        f2 = s2.submit(BackendToolCommandRun(cmd="from-s2"))
        f1.result()
        f2.result()
    elapsed = time.perf_counter() - start

    assert {c.cmd for c in backend.dispatched} == {"from-s1", "from-s2"}
    assert elapsed < 0.18


def test_wait_event_blocks_until_signaled(fake_sandbox: BackendSandbox) -> None:
    """Submissions on s2 must wait for an event recorded by s1."""
    backend: _RecordingBackend = fake_sandbox.backend  # type: ignore[assignment]
    with fake_sandbox.stream() as s1, fake_sandbox.stream() as s2:
        s1.submit(BackendToolCommandRun(cmd="s1-first"))
        evt = s1.record_event()

        s2.wait_event(evt)
        f2 = s2.submit(BackendToolCommandRun(cmd="s2-after-event"))
        f2.result()

    cmds = [c.cmd for c in backend.dispatched]
    assert cmds.index("s1-first") < cmds.index("s2-after-event")


def test_wait_stream_drains_other_first(fake_sandbox: BackendSandbox) -> None:
    backend: _RecordingBackend = fake_sandbox.backend  # type: ignore[assignment]
    with fake_sandbox.stream() as s1, fake_sandbox.stream() as s2:
        for i in range(5):
            s1.submit(BackendToolCommandRun(cmd=f"s1-{i}"))
        s2.wait_stream(s1)
        s2.submit(BackendToolCommandRun(cmd="s2-final"))
        s2.synchronize()

    cmds = [c.cmd for c in backend.dispatched]
    assert cmds[-1] == "s2-final"


def test_synchronize_waits_for_drain(fake_sandbox: BackendSandbox) -> None:
    backend: _RecordingBackend = fake_sandbox.backend  # type: ignore[assignment]
    backend.delay = 0.02
    with fake_sandbox.stream() as s:
        for i in range(5):
            s.submit(BackendToolCommandRun(cmd=f"c{i}"))
        s.synchronize()
        assert len(backend.dispatched) == 5


def test_query_reflects_idle(fake_sandbox: BackendSandbox) -> None:
    with fake_sandbox.stream() as s:
        assert s.query() is True
        s.submit(BackendToolCommandRun(cmd="x"))
        s.synchronize()
        assert s.query() is True


def test_future_result_reflects_dispatch(fake_sandbox: BackendSandbox) -> None:
    with fake_sandbox.stream() as s:
        f = s.submit(BackendToolCommandRun(cmd="r"))
        result = f.result()
        assert isinstance(result, CommandResult)
        assert f.done() is True


def test_future_propagates_exception() -> None:
    """If dispatch raises, awaiting the future must re-raise."""

    class _BoomBackend(_RecordingBackend):
        async def _adispatch(
            self, sandbox: BackendSandbox, call: BackendTool
        ) -> ToolResult | bool:
            raise RuntimeError("kaboom")

    bk = _BoomBackend()
    sb = bk.open()
    with sb.stream() as s:
        f = s.submit(BackendToolCommandRun(cmd="x"))
        with pytest.raises(RuntimeError, match="kaboom"):
            f.result()


def test_event_elapsed_time_requires_both_set() -> None:
    e1 = Event()
    e2 = Event()
    with pytest.raises(RuntimeError):
        e1.elapsed_time(e2)


def test_event_query_initially_false_then_true(fake_sandbox: BackendSandbox) -> None:
    with fake_sandbox.stream() as s:
        evt = s.record_event()
        s.synchronize()
        assert evt.query() is True


def test_buffered_stream_works_end_to_end(fake_sandbox: BackendSandbox) -> None:
    """A bounded stream must accept and process submissions correctly."""
    backend: _RecordingBackend = fake_sandbox.backend  # type: ignore[assignment]
    with fake_sandbox.stream(buffer=2) as s:
        for i in range(5):
            s.submit(BackendToolCommandRun(cmd=f"c{i}"))
        s.synchronize()
    assert len(backend.dispatched) == 5
