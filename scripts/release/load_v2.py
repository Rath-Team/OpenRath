"""Run bounded authenticated lifecycle load against a deployed OpenRath API."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx


@dataclass(frozen=True)
class LoadConfig:
    """Inputs for one immutable target load sample."""

    base_url: str
    token: str
    source_commit: str
    profile: str
    worker_replicas: int
    concurrency: int
    duration_seconds: float
    max_runs: int | None
    poll_interval_seconds: float
    request_timeout_seconds: float
    run_timeout_seconds: float
    target_like: bool


def _origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("base URL must be an HTTP(S) origin without credentials")
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}"


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _lifecycle(
    client: httpx.Client,
    *,
    poll_interval_seconds: float,
    run_timeout_seconds: float,
) -> tuple[bool, str | None, float]:
    started = time.perf_counter()
    try:
        session = client.post("/v1/sessions")
        session.raise_for_status()
        session_id = session.json()["id"]
        run = client.post(
            "/v1/runs",
            headers={"Idempotency-Key": f"ga-load-{uuid4()}"},
            json={
                "assistant_id": "echo",
                "session_id": session_id,
                "state": {"gate_c": True},
            },
        )
        run.raise_for_status()
        run_id = run.json()["id"]
        deadline = time.monotonic() + run_timeout_seconds
        while True:
            response = client.get(f"/v1/runs/{run_id}")
            response.raise_for_status()
            status = response.json().get("status")
            if status == "succeeded":
                return True, None, time.perf_counter() - started
            if status in {"failed", "cancelled", "needs_review"}:
                return False, f"run_{status}", time.perf_counter() - started
            if time.monotonic() >= deadline:
                return False, "run_timeout", time.perf_counter() - started
            time.sleep(poll_interval_seconds)
    except httpx.HTTPStatusError as error:
        return (
            False,
            f"http_{error.response.status_code}",
            time.perf_counter() - started,
        )
    except httpx.TimeoutException:
        return False, "request_timeout", time.perf_counter() - started
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        return False, type(error).__name__, time.perf_counter() - started


def _validate(config: LoadConfig) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", config.source_commit) is None:
        raise ValueError("source_commit must be 40 lowercase hexadecimal characters")
    if config.profile not in {"single_host", "split"}:
        raise ValueError("profile must be single_host or split")
    if config.worker_replicas < 1 or config.concurrency < 1:
        raise ValueError("worker replicas and concurrency must be positive")
    if config.duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    if config.max_runs is not None and config.max_runs < 1:
        raise ValueError("max_runs must be positive")
    if config.poll_interval_seconds < 0:
        raise ValueError("poll_interval_seconds must be non-negative")
    if config.request_timeout_seconds <= 0 or config.run_timeout_seconds <= 0:
        raise ValueError("request and run timeouts must be positive")
    if not config.token:
        raise ValueError("an authentication token is required")
    origin = _origin(config.base_url)
    if config.target_like and not origin.startswith("https://"):
        raise ValueError("target-like load requires an HTTPS base URL")
    return origin


def run_sample(
    config: LoadConfig,
    *,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Execute lifecycles until the duration or maximum run count is reached."""
    target_origin = _validate(config)
    started = time.perf_counter()
    deadline = started + config.duration_seconds
    lock = threading.Lock()
    reserved = 0
    completed = 0
    errors: dict[str, int] = {}
    latencies: list[float] = []

    def worker() -> None:
        nonlocal reserved, completed
        with httpx.Client(
            base_url=target_origin,
            headers={"Authorization": f"Bearer {config.token}"},
            timeout=config.request_timeout_seconds,
            transport=transport,
            trust_env=False,
        ) as client:
            while True:
                with lock:
                    if time.perf_counter() >= deadline or (
                        config.max_runs is not None and reserved >= config.max_runs
                    ):
                        return
                    reserved += 1
                success, error, latency = _lifecycle(
                    client,
                    poll_interval_seconds=config.poll_interval_seconds,
                    run_timeout_seconds=config.run_timeout_seconds,
                )
                with lock:
                    latencies.append(latency)
                    if success:
                        completed += 1
                    else:
                        key = error or "unknown"
                        errors[key] = errors.get(key, 0) + 1

    with ThreadPoolExecutor(max_workers=config.concurrency) as executor:
        futures = [executor.submit(worker) for _ in range(config.concurrency)]
        for future in futures:
            future.result()
    duration = time.perf_counter() - started
    return {
        "schema": "openrath.v2.load-sample/1",
        "source_commit": config.source_commit,
        "profile": config.profile,
        "target_like": config.target_like,
        "worker_replicas": config.worker_replicas,
        "concurrency": config.concurrency,
        "duration_seconds": duration,
        "attempted_runs": reserved,
        "completed_runs": completed,
        "errors": reserved - completed,
        "error_kinds": dict(sorted(errors.items())),
        "throughput_runs_per_second": completed / duration if duration else 0,
        "latency_seconds": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "p99": _percentile(latencies, 0.99),
        },
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "target_origin": target_origin,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token-env", default="OPENRATH_TOKEN")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--profile", choices=["single_host", "split"], required=True)
    parser.add_argument("--worker-replicas", type=int, required=True)
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--duration-seconds", type=float, default=300)
    parser.add_argument("--max-runs", type=int)
    parser.add_argument("--poll-interval-seconds", type=float, default=0.2)
    parser.add_argument("--request-timeout-seconds", type=float, default=20)
    parser.add_argument("--run-timeout-seconds", type=float, default=120)
    parser.add_argument("--target-like", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    token = os.environ.get(args.token_env, "")
    if not token:
        raise SystemExit(
            f"required token environment variable is absent: {args.token_env}"
        )
    try:
        report = run_sample(
            LoadConfig(
                base_url=args.base_url,
                token=token,
                source_commit=args.source_commit,
                profile=args.profile,
                worker_replicas=args.worker_replicas,
                concurrency=args.concurrency,
                duration_seconds=args.duration_seconds,
                max_runs=args.max_runs,
                poll_interval_seconds=args.poll_interval_seconds,
                request_timeout_seconds=args.request_timeout_seconds,
                run_timeout_seconds=args.run_timeout_seconds,
                target_like=args.target_like,
            )
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"completed {report['completed_runs']}/{report['attempted_runs']} "
        f"lifecycles; report: {args.output}"
    )
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
