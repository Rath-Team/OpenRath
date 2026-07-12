"""Loaders that map external benchmark datasets onto BenchmarkTask.

Every loader returns a :class:`~rath.benchmark.loader.LoaderReport`, never a bare
task list: a benchmark score computed over a silently truncated subset is a lie.
"""

from rath.benchmark.datasets.edgebench import load_edgebench
from rath.benchmark.datasets.swebench import (
    SWEBenchVerifier,
    load_swebench,
    swebench_image,
)
from rath.benchmark.datasets.swesmith import load_swesmith
from rath.benchmark.datasets.terminal_bench import load_terminal_bench

__all__ = [
    "SWEBenchVerifier",
    "load_edgebench",
    "load_swebench",
    "load_swesmith",
    "load_terminal_bench",
    "swebench_image",
]
