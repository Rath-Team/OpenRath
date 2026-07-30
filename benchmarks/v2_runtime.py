"""Reproducible local v2 runtime throughput/latency profile."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from rath.context import RunContext
from rath.definition import EffectClass, step
from rath.flow import Workflow
from rath.runtime import LocalRuntime, SQLiteRunStore
from rath.session import Session


class OneStep(Workflow):
    @step(entry=True, effects=EffectClass.READ_ONLY)
    def execute(self, state, context):  # type: ignore[no-untyped-def]
        return {"value": state["value"] + 1}

    def forward(self, session: Session) -> Session:
        return session


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=500)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.runs < 10:
        parser.error("--runs must be at least 10")
    latencies: list[float] = []
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="openrath-benchmark-") as directory:
        store = SQLiteRunStore(Path(directory) / "runtime.db")
        runtime = LocalRuntime(store)
        context = RunContext.local(revision_id=uuid4())
        workflow = OneStep()
        for index in range(args.runs):
            before = time.perf_counter()
            runtime.submit(
                workflow,
                session_id=uuid4(),
                context=context,
                state={"value": index},
            )
            runtime.work_once(worker_id="benchmark")
            latencies.append((time.perf_counter() - before) * 1000)
    duration = time.perf_counter() - started
    report = {
        "schema": "openrath.v2.benchmark/1",
        "profile": "sqlite-single-worker-one-step",
        "runs": args.runs,
        "throughput_runs_per_second": args.runs / duration,
        "latency_ms": {
            "mean": statistics.mean(latencies),
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
    }
    value = json.dumps(report, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(value, encoding="utf-8")
    print(value)


if __name__ == "__main__":
    main()
