"""Loaders that map external benchmark datasets onto BenchmarkTask."""

from rath.benchmark.datasets.swebench import (
    SWEBenchVerifier,
    load_swebench,
    swebench_image,
)
from rath.benchmark.datasets.terminal_bench import load_terminal_bench

__all__ = [
    "SWEBenchVerifier",
    "load_swebench",
    "load_terminal_bench",
    "swebench_image",
]
