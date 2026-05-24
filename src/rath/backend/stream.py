"""Stream and :class:`Event` — threading-based FIFO dispatch bound to one sandbox."""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from types import TracebackType
from typing import Generic, TypeVar, cast

from rath.backend.abc import BackendSandbox
from rath.backend.results import ToolResult
from rath.backend.tool_types import BackendTool

T = TypeVar("T")

_UNSET = object()


class Future(Generic[T]):
    """Blocking handle to the result of a submitted tool call."""

    __slots__ = ("_evt", "_result", "_exc")

    def __init__(self) -> None:
        self._evt = threading.Event()
        self._result: T | object = _UNSET
        self._exc: BaseException | None = None

    def _set_result(self, result: T) -> None:
        self._result = result
        self._evt.set()

    def _set_exception(self, exc: BaseException) -> None:
        self._exc = exc
        self._evt.set()

    def result(self) -> T:
        self._evt.wait()
        if self._exc is not None:
            raise self._exc
        assert self._result is not _UNSET, "Future result was never set"
        return cast(T, self._result)

    def done(self) -> bool:
        return self._evt.is_set()


class Event:
    """Synchronization marker that crosses :class:`Stream` boundaries."""

    __slots__ = ("_thread_evt", "_set_at")

    def __init__(self) -> None:
        self._thread_evt = threading.Event()
        self._set_at: float | None = None

    def _signal(self) -> None:
        self._set_at = time.perf_counter()
        self._thread_evt.set()

    def wait(self) -> None:
        self._thread_evt.wait()

    def query(self) -> bool:
        return self._thread_evt.is_set()

    def synchronize(self) -> None:
        self.wait()

    def elapsed_time(self, end: "Event") -> float:
        if self._set_at is None or end._set_at is None:
            raise RuntimeError(
                "elapsed_time requires both events to have been signaled"
            )
        return (end._set_at - self._set_at) * 1000.0


@dataclass(frozen=True, slots=True)
class _CallOp:
    call: BackendTool
    future: Future[ToolResult | bool]


@dataclass(frozen=True, slots=True)
class _RecordEventOp:
    event: Event


@dataclass(frozen=True, slots=True)
class _WaitEventOp:
    event: Event
    timeout: float | None = None
    future: Future[None] | None = None


@dataclass(frozen=True, slots=True)
class _SyncOp:
    evt: threading.Event


_Op = _CallOp | _RecordEventOp | _WaitEventOp | _SyncOp


class Stream:
    """Per-sandbox FIFO queue of tool-call operations (blocking worker thread).

    Thread-safety contract:

    * Once ``__exit__`` returns, no caller can submit new ops; the worker has
      joined, every future the public methods returned is either done or
      will fail with ``RuntimeError("stream is closed")`` (no hanging).
    * Public methods do their ``_check_closed`` check and the matching
      ``_queue.put`` under the same lock acquisition so a concurrent
      ``__exit__`` cannot enqueue the shutdown signal in between.
    * If the worker hits a fatal exception, ``_fail_remaining`` empties the
      queue and fails every future on it. ``BaseException`` (e.g.
      ``KeyboardInterrupt``) is re-raised after that drain so the worker
      thread terminates with a visible traceback instead of vanishing.
    """

    def __init__(self, sandbox: BackendSandbox, *, buffer: int = 0) -> None:
        self._sandbox = sandbox
        maxsize = 0 if buffer == 0 else buffer
        self._queue: queue.Queue[_Op | None] = queue.Queue(maxsize=maxsize)
        self._worker: threading.Thread | None = None
        self._busy = threading.Event()
        self._closed = False
        self._lock = threading.Lock()

    def __enter__(self) -> Stream:
        with self._lock:
            if self._closed:
                raise RuntimeError("stream is already closed")
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._queue.put(None)
            worker = self._worker
        if worker is not None:
            worker.join(timeout=120.0)

    def _check_closed(self) -> None:
        """Raise if the stream has been closed. Must be called under self._lock."""
        if self._closed:
            raise RuntimeError("stream is closed")

    def submit(self, call: BackendTool) -> Future[ToolResult | bool]:
        future: Future[ToolResult | bool] = Future()
        with self._lock:
            self._check_closed()
            self._queue.put(_CallOp(call=call, future=future))
        return future

    def synchronize(self) -> None:
        done = threading.Event()
        with self._lock:
            self._check_closed()
            self._queue.put(_SyncOp(evt=done))
        done.wait()

    def query(self) -> bool:
        with self._lock:
            self._check_closed()
            return self._queue.empty() and not self._busy.is_set()

    def record_event(self) -> Event:
        event = Event()
        with self._lock:
            self._check_closed()
            self._queue.put(_RecordEventOp(event=event))
        return event

    def wait_event(self, event: Event, *, timeout: float | None = None) -> Future[None]:
        future: Future[None] = Future()
        with self._lock:
            self._check_closed()
            self._queue.put(_WaitEventOp(event=event, timeout=timeout, future=future))
        return future

    def wait_stream(self, other: Stream) -> Future[None]:
        evt = other.record_event()
        return self.wait_event(evt)

    def _run(self) -> None:
        try:
            while True:
                op = self._queue.get()
                if op is None:
                    break
                self._busy.set()
                try:
                    self._handle(op)
                finally:
                    self._busy.clear()
        except Exception as exc:
            # An ordinary exception escaped _handle (which already catches
            # dispatch errors per-op); the worker can't safely continue, so
            # fail any remaining queued futures and exit normally.
            self._fail_remaining(exc)
        except BaseException as fatal:
            # KeyboardInterrupt / SystemExit / MemoryError: fail the
            # remaining futures so callers don't block on .result() forever,
            # then re-raise so the worker thread terminates with a visible
            # traceback instead of vanishing silently.
            self._fail_remaining(fatal)
            raise

    def _fail_remaining(self, exc: BaseException) -> None:
        """Fail every still-queued op's future after a fatal worker error.

        Drains the queue without blocking; ops with no associated future
        (``_RecordEventOp``) are dropped, ``_SyncOp.evt`` is set so its
        waiter unblocks.
        """
        while True:
            try:
                op = self._queue.get_nowait()
            except queue.Empty:
                return
            if op is None:
                return
            if isinstance(op, _CallOp):
                op.future._set_exception(exc)
            elif isinstance(op, _WaitEventOp) and op.future is not None:
                op.future._set_exception(exc)
            elif isinstance(op, _SyncOp):
                op.evt.set()

    def _handle(self, op: _Op) -> None:
        if isinstance(op, _CallOp):
            try:
                result = self._sandbox.dispatch(op.call)
            except BaseException as exc:
                # Set the future regardless of exception class so that even
                # KeyboardInterrupt / SystemExit at dispatch surfaces to the
                # caller's .result() instead of leaving the future hanging.
                # Re-raise non-Exception types so the outer ``_run`` handler
                # can drain remaining queued futures and terminate the worker.
                op.future._set_exception(exc)
                if not isinstance(exc, Exception):
                    raise
            else:
                op.future._set_result(result)
        elif isinstance(op, _RecordEventOp):
            op.event._signal()
        elif isinstance(op, _WaitEventOp):
            signaled = op.event._thread_evt.wait(timeout=op.timeout)
            if op.future is not None:
                if signaled:
                    op.future._set_result(None)
                else:
                    op.future._set_exception(
                        TimeoutError(f"wait_event timed out after {op.timeout}s")
                    )
        elif isinstance(op, _SyncOp):
            op.evt.set()
