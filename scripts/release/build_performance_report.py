"""Combine target load samples into the OpenRath GA performance gate report."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .record_gate import build_report as build_gate_report
except ImportError:  # pragma: no cover - direct script execution
    from record_gate import build_report as build_gate_report

REQUIRED_PROFILES = {
    ("single_host", 1),
    ("split", 1),
    ("split", 2),
    ("split", 4),
}


def _load_sample(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"load sample must be a JSON object: {path}")
    if value.get("schema") != "openrath.v2.load-sample/1":
        raise ValueError(f"unsupported load sample schema: {path}")
    return value


def build_report(
    *,
    sample_paths: list[Path],
    evidence_root: Path,
    environment_profile: str,
    minimum_sample_seconds: float = 300,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a passing report from single-host and 1/2/4-worker split samples."""
    if len(sample_paths) != 4:
        raise ValueError("exactly four load samples are required")
    samples: dict[tuple[str, int], dict[str, Any]] = {}
    commits: set[str] = set()
    for path in sample_paths:
        sample = _load_sample(path)
        profile = sample.get("profile")
        replicas = sample.get("worker_replicas")
        if (
            not isinstance(profile, str)
            or isinstance(replicas, bool)
            or not isinstance(replicas, int)
        ):
            raise ValueError(f"invalid profile or worker count: {path}")
        key = (profile, replicas)
        if key in samples:
            raise ValueError(f"duplicate load profile: {profile}/{replicas}")
        samples[key] = sample
        commit = sample.get("source_commit")
        if not isinstance(commit, str):
            raise ValueError(f"load sample source_commit is missing: {path}")
        commits.add(commit)
        if sample.get("target_like") is not True:
            raise ValueError(f"load sample is not target-like: {path}")
        if sample.get("errors") != 0:
            raise ValueError("performance samples must contain zero errors")
        completed = sample.get("completed_runs")
        if (
            isinstance(completed, bool)
            or not isinstance(completed, int)
            or completed < 1
        ):
            raise ValueError("performance samples require at least one completed run")
        duration = sample.get("duration_seconds")
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or duration < minimum_sample_seconds
        ):
            raise ValueError(
                f"performance sample must run at least {minimum_sample_seconds} seconds"
            )
        throughput = sample.get("throughput_runs_per_second")
        if (
            isinstance(throughput, bool)
            or not isinstance(throughput, (int, float))
            or throughput <= 0
        ):
            raise ValueError(f"load sample throughput is missing: {path}")
    if set(samples) != REQUIRED_PROFILES:
        raise ValueError("samples must cover single-host and split 1/2/4 workers")
    if len(commits) != 1:
        raise ValueError("all performance samples must use the same source commit")

    split_one = float(samples[("split", 1)]["throughput_runs_per_second"])
    split_two = float(samples[("split", 2)]["throughput_runs_per_second"])
    split_four = float(samples[("split", 4)]["throughput_runs_per_second"])
    if split_one <= 0:
        raise ValueError("one-worker throughput must be positive")
    two_efficiency = split_two / (split_one * 2)
    four_efficiency = split_four / (split_one * 4)
    if four_efficiency < 0.70:
        raise ValueError("four-worker scaling efficiency must be at least 0.70")

    details: dict[str, object] = {
        "single_host": "passed",
        "split_profile": "passed",
        "worker_scaling_efficiency": four_efficiency,
        "two_worker_scaling_efficiency": two_efficiency,
        "throughput_runs_per_second": {
            f"{profile}_{replicas}": sample["throughput_runs_per_second"]
            for (profile, replicas), sample in sorted(samples.items())
        },
    }
    source_commit = commits.pop()
    return build_gate_report(
        gate="performance",
        source_commit=source_commit,
        environment={"profile": environment_profile, "target_like": True},
        details=details,
        evidence_root=evidence_root,
        evidence_files=sample_paths,
        open_risks=[],
        generated_at=generated_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--single-host", type=Path, required=True)
    parser.add_argument("--split-one", type=Path, required=True)
    parser.add_argument("--split-two", type=Path, required=True)
    parser.add_argument("--split-four", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--environment-profile", required=True)
    parser.add_argument("--minimum-sample-seconds", type=float, default=300)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_report(
            sample_paths=[
                args.single_host,
                args.split_one,
                args.split_two,
                args.split_four,
            ],
            evidence_root=args.evidence_root,
            environment_profile=args.environment_profile,
            minimum_sample_seconds=args.minimum_sample_seconds,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"recorded performance Gate C report at {args.output}")


if __name__ == "__main__":
    main()
