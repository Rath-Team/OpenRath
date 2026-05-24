#!/usr/bin/env python
"""Soak / stress harness for the OpenRath async runtime.

Drives N concurrent session loops against a real backend (and optionally a
real LLM) for ``--duration`` seconds and emits a metrics blob to
``--metrics-out``. Designed to surface scheduler regressions, leaks,
backpressure misbehaviour, and runtime-loop saturation — the failure
modes that unit tests can't reasonably cover.

Examples
========

LocalBackend, scripted LLM, 60 seconds, 8 concurrent sessions, fan-out 16:

    python scripts/stress.py \\
        --backend local --llm scripted \\
        --sessions 8 --tool-fanout 16 --duration 60 \\
        --metrics-out runs/stress-local.json

Real OpenSandbox + real OpenAI, longer soak:

    python scripts/stress.py \\
        --backend opensandbox --llm openai \\
        --sessions 4 --tool-fanout 8 --duration 300 \\
        --metrics-out runs/stress-opensandbox.json

Metrics emitted
===============

JSON blob with:

- throughput.{tool_dispatches, completions, session_loops}_per_s
- latency.{dispatch, complete, loop}_ms.{p50, p95, p99}
- loop_lag_ms.{p50, p95, max} — heartbeat task scheduling delay
- pending_depth.{max, samples} — live ``_pending`` Session count
- counts.{submitted, completed, cancelled, errored} — must sum-conserve
- process.{peak_rss_mb, peak_threads, peak_fds (POSIX only)}

The script never falls back to mocks — backends and LLMs are real.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rath._async.aloop import _arun_session_loop
from rath._async.runtime import OpenRathRuntime, runtime
from rath.backend.local import LocalBackend
from rath.flow.agent_param import AgentParam, Provider
from rath.flow.tool import FlowToolCall
from rath.llm import (
    RathLLMAssistantMessage,
    RathLLMChatChoice,
    RathLLMChatRequest,
    RathLLMChatResponse,
    RathLLMFunctionTool,
    RathLLMToolCallFunction,
    RathLLMToolCallPart,
)
from rath.session import Session, session_registry


# --------------------------------------------------------------------- metrics


@dataclass
class _Metrics:
    """Aggregated counters and latency samples for the soak run."""

    submitted: int = 0
    completed: int = 0
    cancelled: int = 0
    errored: int = 0
    dispatch_ms: list[float] = field(default_factory=list)
    complete_ms: list[float] = field(default_factory=list)
    loop_ms: list[float] = field(default_factory=list)
    loop_lag_ms: list[float] = field(default_factory=list)
    pending_samples: list[int] = field(default_factory=list)
    peak_rss_mb: float = 0.0
    peak_threads: int = 0
    peak_fds: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add_loop_sample(self, ms: float, *, errored: bool, cancelled: bool) -> None:
        with self.lock:
            self.loop_ms.append(ms)
            if errored:
                self.errored += 1
            elif cancelled:
                self.cancelled += 1
            else:
                self.completed += 1

    def add_lag(self, ms: float) -> None:
        with self.lock:
            self.loop_lag_ms.append(ms)

    def add_pending(self, n: int) -> None:
        with self.lock:
            self.pending_samples.append(n)


def _pct(samples: list[float], p: float) -> float:
    if not samples:
        return 0.0
    s = sorted(samples)
    idx = max(0, min(len(s) - 1, int(round(p / 100 * (len(s) - 1)))))
    return float(s[idx])


def _summary(metrics: _Metrics, duration_s: float) -> dict[str, Any]:
    def lat(name: str, samples: list[float]) -> dict[str, float]:
        return {
            "p50": _pct(samples, 50),
            "p95": _pct(samples, 95),
            "p99": _pct(samples, 99),
            "count": len(samples),
        }

    return {
        "duration_s": duration_s,
        "counts": {
            "submitted": metrics.submitted,
            "completed": metrics.completed,
            "cancelled": metrics.cancelled,
            "errored": metrics.errored,
        },
        "counts_sum_conserved": (
            metrics.submitted
            == metrics.completed + metrics.cancelled + metrics.errored
        ),
        "throughput": {
            "session_loops_per_s": metrics.completed / duration_s if duration_s else 0.0,
            "completions_per_s": len(metrics.complete_ms) / duration_s
            if duration_s
            else 0.0,
            "dispatches_per_s": len(metrics.dispatch_ms) / duration_s
            if duration_s
            else 0.0,
        },
        "latency_ms": {
            "dispatch": lat("dispatch", metrics.dispatch_ms),
            "complete": lat("complete", metrics.complete_ms),
            "loop": lat("loop", metrics.loop_ms),
        },
        "loop_lag_ms": {
            "p50": _pct(metrics.loop_lag_ms, 50),
            "p95": _pct(metrics.loop_lag_ms, 95),
            "max": max(metrics.loop_lag_ms) if metrics.loop_lag_ms else 0.0,
            "samples": len(metrics.loop_lag_ms),
        },
        "pending_depth": {
            "max": max(metrics.pending_samples) if metrics.pending_samples else 0,
            "mean": (
                statistics.fmean(metrics.pending_samples)
                if metrics.pending_samples
                else 0.0
            ),
            "samples": len(metrics.pending_samples),
        },
        "process": {
            "peak_rss_mb": metrics.peak_rss_mb,
            "peak_threads": metrics.peak_threads,
            "peak_fds": metrics.peak_fds,
        },
    }


# --------------------------------------------------------------------- scripted bits


class _ScriptedAsyncExecutor:
    """Cycling scripted LLM for ``--llm scripted`` runs."""

    __slots__ = ("_template_tool_round", "_template_stop", "_state")

    def __init__(self, fanout: int) -> None:
        # Each "session loop" produces one tool round (fanout tool_calls)
        # followed by one stop. We reset state per session loop externally.
        self._template_tool_round = fanout
        self._template_stop = True
        self._state = 0

    async def acomplete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
        # Round 0: tool calls; round 1: stop.
        if self._state == 0:
            self._state = 1
            parts = tuple(
                RathLLMToolCallPart(
                    id=f"tc{i}",
                    type="function",
                    function=RathLLMToolCallFunction(
                        name="cheap_write",
                        arguments=json.dumps(
                            {"path": f"stress_{i}.txt", "content": "x"}
                        ),
                        arguments_parsed={
                            "path": f"stress_{i}.txt",
                            "content": "x",
                        },
                        arguments_parse_error=False,
                    ),
                )
                for i in range(self._template_tool_round)
            )
            return RathLLMChatResponse(
                id="r-tool",
                choices=(
                    RathLLMChatChoice(
                        index=0,
                        finish_reason="tool_calls",
                        message=RathLLMAssistantMessage(content=None, tool_calls=parts),
                    ),
                ),
                created=1,
                model="scripted",
            )
        return RathLLMChatResponse(
            id="r-stop",
            choices=(
                RathLLMChatChoice(
                    index=0,
                    finish_reason="stop",
                    message=RathLLMAssistantMessage(content="done"),
                ),
            ),
            created=1,
            model="scripted",
        )

    async def adispatch_tool(
        self,
        session: Session,
        tool: FlowToolCall,
        arguments: dict[str, Any],
    ) -> Any:
        return await asyncio.to_thread(tool, session, dict(arguments or {}))

    def tool_schemas(self) -> tuple[RathLLMFunctionTool, ...]:
        return ()


class _CheapWriteTool(FlowToolCall):
    """Parallel-safe fs:write — distinct paths overlap, same paths serialise."""

    parallel_safe = True

    def resource_key(self, arguments: Any) -> tuple[str, ...]:
        return ("fs:write", str(arguments["path"]))

    @property
    def name(self) -> str:
        return "cheap_write"

    @property
    def parameters(self) -> Any:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        }

    def __call__(self, session: Session, arguments: Any) -> Any:
        sb = session.require_sandbox()
        from rath.backend.tool_types import BackendToolFilesWrite

        return sb.dispatch(
            BackendToolFilesWrite(path=str(arguments["path"]), data=str(arguments["content"]))
        )


# --------------------------------------------------------------------- backends


def _make_backend(name: str) -> Any:
    if name == "local":
        return LocalBackend()
    if name == "opensandbox":
        from rath.backend.opensandbox import OpenSandboxBackend

        return OpenSandboxBackend()
    raise ValueError(f"unknown backend {name!r}")


def _make_llm_executor(name: str, fanout: int) -> Any:
    if name == "scripted":
        # Returns a *factory* so each session loop gets a fresh state machine.
        def _factory() -> _ScriptedAsyncExecutor:
            return _ScriptedAsyncExecutor(fanout=fanout)

        return _factory
    if name == "openai":
        from rath._async.aopenai import RathOpenAIAsyncChatClient
        from rath.llm.provider import Provider as _LLMProvider

        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise SystemExit("--llm openai requires OPENAI_API_KEY")
        base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
        model = os.environ.get("OPENAI_DEFAULT_MODEL", "").strip() or None
        provider = _LLMProvider(api_key=api_key, base_url=base_url, model=model)
        client = RathOpenAIAsyncChatClient(provider)

        # Wrap as a scheduler-compatible executor.
        class _LiveExecutor:
            async def acomplete(self, req: RathLLMChatRequest) -> RathLLMChatResponse:
                return await client.acomplete(req)

            async def adispatch_tool(
                self,
                session: Session,
                tool: FlowToolCall,
                arguments: Any,
            ) -> Any:
                return await asyncio.to_thread(tool, session, dict(arguments or {}))

            def tool_schemas(self) -> tuple[RathLLMFunctionTool, ...]:
                return ()

        def _factory() -> _LiveExecutor:
            return _LiveExecutor()

        return _factory
    raise ValueError(f"unknown llm {name!r}")


# --------------------------------------------------------------------- workers


def _process_metrics() -> dict[str, float]:
    rss_mb = 0.0
    fds = 0
    try:
        import resource  # type: ignore[import-not-found]

        ru = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is KB on Linux, bytes on macOS
        if sys.platform == "darwin":
            rss_mb = ru.ru_maxrss / (1024 * 1024)
        else:
            rss_mb = ru.ru_maxrss / 1024
    except Exception:
        pass
    if sys.platform != "win32":
        try:
            fds = len(os.listdir(f"/proc/{os.getpid()}/fd"))
        except Exception:
            fds = 0
    return {"rss_mb": rss_mb, "fds": float(fds)}


def _heartbeat_loop(metrics: _Metrics, stop: threading.Event) -> None:
    """Submit a no-op coroutine every 100ms and record scheduling lag."""

    async def _noop() -> float:
        return time.perf_counter()

    rt = runtime()
    while not stop.is_set():
        t0 = time.perf_counter()
        fut = rt.submit(_noop())
        try:
            t1 = fut.result(timeout=5.0)
            lag_ms = max(0.0, (t1 - t0) * 1000.0)
            metrics.add_lag(lag_ms)
        except Exception:
            pass
        stop.wait(0.1)


def _sampler_loop(metrics: _Metrics, stop: threading.Event) -> None:
    """Sample process stats + pending Session count every second."""
    reg = session_registry()
    while not stop.is_set():
        # Pending depth: live sessions whose _pending is not None.
        with reg._lock:  # type: ignore[attr-defined]
            sessions = list(reg._by_id.values())  # type: ignore[attr-defined]
        pending = sum(1 for s in sessions if getattr(s, "_pending", None) is not None)
        metrics.add_pending(pending)
        # Process resource peaks.
        proc = _process_metrics()
        with metrics.lock:
            metrics.peak_rss_mb = max(metrics.peak_rss_mb, proc["rss_mb"])
            metrics.peak_threads = max(metrics.peak_threads, threading.active_count())
            metrics.peak_fds = max(metrics.peak_fds, int(proc["fds"]))
        stop.wait(1.0)


def _session_worker(
    metrics: _Metrics,
    stop: threading.Event,
    *,
    backend: Any,
    executor_factory: Any,
    fanout: int,
    tool: FlowToolCall,
) -> None:
    """One thread = one looping session-loop submitter."""
    while not stop.is_set():
        sb = backend.open()
        try:
            agent = AgentParam(Session.from_agent_prompt("stress"), Provider())
            user = Session.from_user_message("stress").bind_sandbox(sb)
            executor = executor_factory()
            with metrics.lock:
                metrics.submitted += 1
            t0 = time.perf_counter()
            errored = False
            cancelled = False
            try:
                runtime().run(
                    _arun_session_loop(
                        user,
                        agent.agent_session,
                        agent_provider=agent.provider,
                        executor=executor,
                        tools=[tool],
                    )
                )
            except BaseException:
                # Cancellation, runtime shutdown, or genuine error.
                if stop.is_set():
                    cancelled = True
                else:
                    errored = True
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            metrics.add_loop_sample(elapsed_ms, errored=errored, cancelled=cancelled)
        finally:
            try:
                backend.close(sb)
            except Exception:
                pass


# --------------------------------------------------------------------- CLI


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OpenRath async-runtime soak harness."
    )
    parser.add_argument(
        "--backend",
        choices=["local", "opensandbox"],
        default="local",
        help="Real backend; both run actual subprocesses / sandbox calls.",
    )
    parser.add_argument(
        "--llm",
        choices=["scripted", "openai"],
        default="scripted",
        help="LLM driver; 'scripted' emits a fanout-of-tool-calls + stop "
        "cycle, 'openai' hits the real OpenAI API (set OPENAI_API_KEY).",
    )
    parser.add_argument(
        "--sessions",
        type=int,
        default=4,
        help="Concurrent worker threads, each running a tight loop of "
        "session-loop submissions.",
    )
    parser.add_argument(
        "--tool-fanout",
        type=int,
        default=8,
        help="Number of parallel-safe ``cheap_write`` tool_calls per "
        "scripted assistant round.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=60.0,
        help="Soak duration in seconds.",
    )
    parser.add_argument(
        "--metrics-out",
        type=Path,
        default=Path("runs/stress.json"),
        help="Where to write the metrics JSON blob.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    args.metrics_out.parent.mkdir(parents=True, exist_ok=True)

    backend = _make_backend(args.backend)
    executor_factory = _make_llm_executor(args.llm, args.tool_fanout)
    tool = _CheapWriteTool()
    metrics = _Metrics()

    stop = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat_loop,
        args=(metrics, stop),
        name="stress-heartbeat",
        daemon=True,
    )
    sampler = threading.Thread(
        target=_sampler_loop,
        args=(metrics, stop),
        name="stress-sampler",
        daemon=True,
    )
    heartbeat.start()
    sampler.start()

    workers = [
        threading.Thread(
            target=_session_worker,
            args=(metrics, stop),
            kwargs={
                "backend": backend,
                "executor_factory": executor_factory,
                "fanout": args.tool_fanout,
                "tool": tool,
            },
            name=f"stress-worker-{i}",
            daemon=True,
        )
        for i in range(args.sessions)
    ]
    t_start = time.perf_counter()
    for w in workers:
        w.start()

    try:
        time.sleep(args.duration)
    except KeyboardInterrupt:
        print("Interrupted; tearing down…", file=sys.stderr)
    finally:
        stop.set()
        # Workers exit on their next loop check; give them a bounded grace
        # period, then count anything still alive as cancelled.
        for w in workers:
            w.join(timeout=10.0)
        heartbeat.join(timeout=2.0)
        sampler.join(timeout=2.0)

    duration_s = time.perf_counter() - t_start

    # Best-effort runtime drain so the JSON output reflects a quiesced state.
    try:
        cancelled_now = runtime().drain(5.0)
        with metrics.lock:
            metrics.cancelled += int(cancelled_now)
    except Exception:
        pass

    blob = _summary(metrics, duration_s)
    blob["config"] = {
        "backend": args.backend,
        "llm": args.llm,
        "sessions": args.sessions,
        "tool_fanout": args.tool_fanout,
        "duration_s": args.duration,
    }
    args.metrics_out.write_text(json.dumps(blob, indent=2), encoding="utf-8")
    print(json.dumps(blob, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
