from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import httpx
import pytest

from scripts.release import build_performance_report, load_v2

SOURCE_COMMIT = "d" * 40


def test_load_sample_completes_lifecycles_without_recording_token() -> None:
    lock = threading.Lock()
    sequence = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sequence
        assert request.headers["authorization"] == "Bearer super-secret"
        with lock:
            sequence += 1
            current = sequence
        if request.method == "POST" and request.url.path == "/v1/sessions":
            return httpx.Response(201, json={"id": f"session-{current}"})
        if request.method == "POST" and request.url.path == "/v1/runs":
            return httpx.Response(201, json={"id": f"run-{current}"})
        if request.method == "GET" and request.url.path.startswith("/v1/runs/"):
            return httpx.Response(200, json={"status": "succeeded"})
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    report = load_v2.run_sample(
        load_v2.LoadConfig(
            base_url="https://target.example",
            token="super-secret",
            source_commit=SOURCE_COMMIT,
            profile="split",
            worker_replicas=4,
            concurrency=2,
            duration_seconds=60,
            max_runs=4,
            poll_interval_seconds=0,
            request_timeout_seconds=2,
            run_timeout_seconds=2,
            target_like=True,
        ),
        transport=httpx.MockTransport(handler),
    )

    assert report["completed_runs"] == 4
    assert report["errors"] == 0
    assert report["worker_replicas"] == 4
    assert report["throughput_runs_per_second"] > 0
    assert "super-secret" not in json.dumps(report)


def test_target_like_load_requires_https() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        load_v2.run_sample(
            load_v2.LoadConfig(
                base_url="http://target.example",
                token="super-secret",
                source_commit=SOURCE_COMMIT,
                profile="split",
                worker_replicas=1,
                concurrency=1,
                duration_seconds=1,
                max_runs=1,
                poll_interval_seconds=0,
                request_timeout_seconds=1,
                run_timeout_seconds=1,
                target_like=True,
            )
        )


def _sample(
    *,
    profile: str,
    replicas: int,
    throughput: float,
    errors: int = 0,
) -> dict[str, Any]:
    return {
        "schema": "openrath.v2.load-sample/1",
        "source_commit": SOURCE_COMMIT,
        "profile": profile,
        "target_like": True,
        "worker_replicas": replicas,
        "duration_seconds": 300.0,
        "attempted_runs": 100,
        "completed_runs": 100 - errors,
        "errors": errors,
        "throughput_runs_per_second": throughput,
        "latency_seconds": {"p50": 0.1, "p95": 0.2, "p99": 0.3},
        "generated_at": "2026-07-30T12:00:00Z",
        "target_origin": "https://target.example",
    }


def _write_samples(root: Path, samples: list[dict[str, Any]]) -> list[Path]:
    paths: list[Path] = []
    for index, sample in enumerate(samples):
        path = root / f"sample-{index}.json"
        path.write_text(json.dumps(sample), encoding="utf-8")
        paths.append(path)
    return paths


def test_performance_report_requires_single_and_split_scaling_samples(
    tmp_path: Path,
) -> None:
    paths = _write_samples(
        tmp_path,
        [
            _sample(profile="single_host", replicas=1, throughput=8),
            _sample(profile="split", replicas=1, throughput=10),
            _sample(profile="split", replicas=2, throughput=18),
            _sample(profile="split", replicas=4, throughput=30),
        ],
    )

    report = build_performance_report.build_report(
        sample_paths=paths,
        evidence_root=tmp_path,
        environment_profile="staging-us-east",
        generated_at="2026-07-30T13:00:00Z",
    )

    details = report["details"]
    assert details["single_host"] == "passed"
    assert details["split_profile"] == "passed"
    assert details["worker_scaling_efficiency"] == pytest.approx(0.75)
    assert report["source_commit"] == SOURCE_COMMIT
    assert len(report["evidence"]) == 4


def test_performance_report_rejects_errors_and_insufficient_scaling(
    tmp_path: Path,
) -> None:
    samples = [
        _sample(profile="single_host", replicas=1, throughput=8),
        _sample(profile="split", replicas=1, throughput=10),
        _sample(profile="split", replicas=2, throughput=18),
        _sample(profile="split", replicas=4, throughput=20),
    ]
    paths = _write_samples(tmp_path, samples)
    with pytest.raises(ValueError, match="scaling efficiency"):
        build_performance_report.build_report(
            sample_paths=paths,
            evidence_root=tmp_path,
            environment_profile="staging-us-east",
        )

    samples[-1] = _sample(
        profile="split",
        replicas=4,
        throughput=32,
        errors=1,
    )
    paths[-1].write_text(json.dumps(samples[-1]), encoding="utf-8")
    with pytest.raises(ValueError, match="zero errors"):
        build_performance_report.build_report(
            sample_paths=paths,
            evidence_root=tmp_path,
            environment_profile="staging-us-east",
        )

    samples[-1] = _sample(profile="split", replicas=4, throughput=32)
    samples[-1]["completed_runs"] = 0
    paths[-1].write_text(json.dumps(samples[-1]), encoding="utf-8")
    with pytest.raises(ValueError, match="completed run"):
        build_performance_report.build_report(
            sample_paths=paths,
            evidence_root=tmp_path,
            environment_profile="staging-us-east",
        )
