"""Run a bounded local soak profile and report resource growth."""

from __future__ import annotations

import argparse
import json
import platform
import tempfile
import threading
import time
import tracemalloc
from pathlib import Path
from uuid import uuid4

from rath.context import RunContext
from rath.definition import EffectClass, step
from rath.flow import Workflow
from rath.runtime import LocalRuntime, RunStatus, SQLiteRunStore
from rath.session import Session


class SoakWorkflow(Workflow):
    @step(entry=True, effects=EffectClass.READ_ONLY)
    def execute(self, state, context):  # type: ignore[no-untyped-def]
        return {"value": int(state["value"]) + 1}

    def forward(self, session: Session) -> Session:
        return session


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-seconds", type=float, default=300)
    parser.add_argument("--max-runs", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.duration_seconds <= 0:
        parser.error("--duration-seconds must be positive")
    if args.max_runs is not None and args.max_runs < 1:
        parser.error("--max-runs must be positive")

    started = time.perf_counter()
    deadline = started + args.duration_seconds
    completed = 0
    failures = 0
    threads_before = threading.active_count()
    tracemalloc.start()
    memory_before, _ = tracemalloc.get_traced_memory()
    with tempfile.TemporaryDirectory(prefix="openrath-soak-") as directory:
        store = SQLiteRunStore(Path(directory) / "runtime.db")
        runtime = LocalRuntime(store)
        context = RunContext.local(revision_id=uuid4())
        workflow = SoakWorkflow()
        while time.perf_counter() < deadline and (
            args.max_runs is None or completed + failures < args.max_runs
        ):
            runtime.submit(
                workflow,
                session_id=uuid4(),
                context=context,
                state={"value": completed + failures},
            )
            run = runtime.work_once(worker_id="soak")
            if run is not None and run.status is RunStatus.SUCCEEDED:
                completed += 1
            else:
                failures += 1
        store.close()
    memory_after, memory_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    duration = time.perf_counter() - started
    report = {
        "schema": "openrath.v2.soak/1",
        "profile": "sqlite-single-worker-one-step",
        "duration_seconds": duration,
        "completed_runs": completed,
        "failed_runs": failures,
        "throughput_runs_per_second": completed / duration,
        "resource_delta": {
            "threads": threading.active_count() - threads_before,
            "traced_memory_bytes": memory_after - memory_before,
            "peak_traced_memory_bytes": memory_peak,
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "scope": (
            "Review profile only; repeat for the approved 8h/24h duration "
            "on target hardware before production rollout."
        ),
    }
    value = json.dumps(report, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(value, encoding="utf-8")
    print(value)
    if failures:
        raise SystemExit(1)
    if report["resource_delta"]["threads"] != 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
