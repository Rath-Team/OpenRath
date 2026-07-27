"""Conservative capacity worksheet for an OpenRath v2 deployment."""

from __future__ import annotations

import argparse
import json
import math


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--peak-runs-per-second", type=float, required=True)
    parser.add_argument("--mean-run-seconds", type=float, required=True)
    parser.add_argument("--events-per-run", type=float, default=10)
    parser.add_argument("--event-kib", type=float, default=2)
    parser.add_argument("--retention-days", type=int, default=30)
    parser.add_argument("--worker-concurrency", type=int, default=16)
    parser.add_argument("--headroom", type=float, default=1.5)
    args = parser.parse_args()
    if min(
        args.peak_runs_per_second,
        args.mean_run_seconds,
        args.events_per_run,
        args.event_kib,
        args.worker_concurrency,
        args.headroom,
    ) <= 0:
        parser.error("capacity inputs must be positive")
    concurrent = (
        args.peak_runs_per_second * args.mean_run_seconds * args.headroom
    )
    workers = math.ceil(concurrent / args.worker_concurrency)
    events_per_day = args.peak_runs_per_second * 86400 * args.events_per_run
    storage_gib = (
        events_per_day
        * args.retention_days
        * args.event_kib
        * args.headroom
        / 1024
        / 1024
    )
    report = {
        "estimated_concurrent_runs": math.ceil(concurrent),
        "minimum_worker_replicas": max(2, workers),
        "suggested_postgres_connections": max(20, workers * 4 + 10),
        "event_storage_gib_before_indexes": round(storage_gib, 2),
        "warning": (
            "Worksheet only; validate with the actual workflow/provider mix "
            "and database benchmark before production."
        ),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
