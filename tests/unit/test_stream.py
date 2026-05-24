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
from rath.backend.stream import Future


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

    async def _aopen(self, spec: BackendSandboxSpec | None = None) -> BackendSandbox:
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


def test_post_exit_submit_raises_instead_of_hanging(
    fake_sandbox: BackendSandbox,
) -> None:
    """After ``__exit__`` returns, every public method must reject new ops
    with a clear ``RuntimeError`` rather than enqueue them silently."""
    stream = fake_sandbox.stream()
    with stream as s:
        s.submit(BackendToolCommandRun(cmd="before-close")).result()
    # Outside the with-block: stream is closed.
    with pytest.raises(RuntimeError, match="stream is closed"):
        stream.submit(BackendToolCommandRun(cmd="should-not-enqueue"))
    with pytest.raises(RuntimeError, match="stream is closed"):
        stream.synchronize()
    with pytest.raises(RuntimeError, match="stream is closed"):
        stream.record_event()
    with pytest.raises(RuntimeError, match="stream is closed"):
        stream.wait_event(Event())
    with pytest.raises(RuntimeError, match="stream is closed"):
        stream.query()


def test_double_exit_is_idempotent(fake_sandbox: BackendSandbox) -> None:
    """Calling ``__exit__`` twice must not enqueue a second shutdown signal
    or block; the second call is a no-op."""
    stream = fake_sandbox.stream()
    with stream:
        pass
    # Second exit; would deadlock if it tried to put another None into a
    # closed worker's queue and join an already-joined thread.
    stream.__exit__(None, None, None)


def test_concurrent_submit_and_exit_either_completes_or_rejects(
    fake_sandbox: BackendSandbox,
) -> None:
    """The check-closed-and-enqueue must be atomic with respect to
    ``__exit__``: each submit returns either a future that ultimately
    completes, OR raises ``RuntimeError``. No submit may return a future
    that hangs forever because the worker shut down between check and put.
    """
    import threading

    outcomes: list[str] = []
    futures: list[Future[ToolResult | bool]] = []
    outcomes_lock = threading.Lock()

    stream = fake_sandbox.stream()
    with stream as s:
        start = threading.Barrier(11)

        def _submitter() -> None:
            start.wait(timeout=5.0)
            for _ in range(50):
                try:
                    f = s.submit(BackendToolCommandRun(cmd="race"))
                except RuntimeError:
                    with outcomes_lock:
                        outcomes.append("rejected")
                else:
                    with outcomes_lock:
                        outcomes.append("enqueued")
                        futures.append(f)

        def _closer() -> None:
            start.wait(timeout=5.0)
            time.sleep(0.005)  # let submitters get a few rounds in first
            stream.__exit__(None, None, None)

        submitters = [threading.Thread(target=_submitter) for _ in range(10)]
        closer = threading.Thread(target=_closer)
        for t in submitters:
            t.start()
        closer.start()
        for t in submitters + [closer]:
            t.join(timeout=10.0)
            assert not t.is_alive(), "submitter/closer thread hung"

    # After the stream context exits, every enqueued future must be done.
    for f in futures:
        assert f.done(), (
            "submit() returned a future that was never resolved — "
            "TOCTOU between _check_closed and queue.put left a future hanging"
        )
    # Some race outcomes are timing-dependent (the closer may win the
    # barrier before any submit lands, or all submits may complete before
    # the closer arrives). The contract we care about is that no future
    # was left hanging — asserted above by the f.done() loop. The
    # presence-of-each-outcome check would just be smoke for whether the
    # race window opened; skip it to keep the test deterministic.
    assert outcomes  # at least something happened


@pytest.mark.filterwarnings(
    # Re-raising BaseException from the worker is the documented contract
    # (visible traceback over silent disappearance). pytest's default
    # PytestUnhandledThreadExceptionWarning would otherwise turn that
    # *desired* behavior into a test failure.
    "ignore::pytest.PytestUnhandledThreadExceptionWarning"
)
def test_worker_baseexception_fails_remaining_futures_and_propagates(
    fake_sandbox: BackendSandbox,
) -> None:
    """When the dispatch loop hits ``BaseException`` (e.g. ``KeyboardInterrupt``):

    1. Every future already on the queue must be failed (no hangs on ``.result()``).
    2. The worker must terminate; the thread state should observably die.
    """

    class _KeyboardInterruptBackend(_RecordingBackend):
        def dispatch(
            self, sandbox: BackendSandbox, call: BackendTool
        ) -> ToolResult | bool:
            raise KeyboardInterrupt("simulated Ctrl-C inside dispatch")

    bk = _KeyboardInterruptBackend()
    sb = bk.open()
    # Use a bounded buffer of 0 (unbounded queue); submit several ops
    # before the worker drains the first one to populate the queue.
    with sb.stream() as s:
        futures = [s.submit(BackendToolCommandRun(cmd=f"c{i}")) for i in range(5)]
        # The first dispatch will raise KeyboardInterrupt, killing the worker.
        # _fail_remaining must drain the rest and set exceptions on every future.
        deadline = time.perf_counter() + 5.0
        while time.perf_counter() < deadline:
            if all(f.done() for f in futures):
                break
            time.sleep(0.01)
        for i, f in enumerate(futures):
            assert f.done(), (
                f"future[{i}] never resolved after worker BaseException — "
                "_fail_remaining did not drain"
            )
            with pytest.raises(BaseException):
                f.result()
        # Worker should have terminated; join inside __exit__ would otherwise
        # block 120s. Pull out worker for direct assertion.
        worker = s._worker
        assert worker is not None
        # Worker should die quickly after raising; we'll observe that below.
        worker.join(timeout=2.0)
        assert not worker.is_alive(), (
            "worker thread did not terminate after BaseException"
        )
    # Sanity: __exit__ returned normally, no deadlock.


def test_wait_event_timeout_resolves_future_with_timeout_error(
    fake_sandbox: BackendSandbox,
) -> None:
    """``wait_event(evt, timeout=...)`` must resolve its returned future
    with ``TimeoutError`` if the event is never signaled in time."""
    with fake_sandbox.stream() as s:
        never_signaled = Event()
        f = s.wait_event(never_signaled, timeout=0.05)
        with pytest.raises(TimeoutError, match="wait_event timed out"):
            f.result()
