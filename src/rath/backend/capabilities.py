"""Static backend capability description."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class IsolationLevel(str, Enum):
    """Isolation level offered by the backend's runtime."""

    PROCESS = "process"
    CONTAINER = "container"
    MICROVM = "microvm"
    VM = "vm"


class BackendCapability(str, Enum):
    """Optional backend features a benchmark task may require.

    A task that needs one of these and lands on a backend that lacks it cannot
    run. Saying so before the episode starts is the difference between a
    reported coverage gap and a mystery failure halfway through a rollout.
    """

    PER_TASK_IMAGE = "per_task_image"
    """Open a sandbox from an image named by the task, not by global config."""

    NETWORK_ISOLATION = "network_isolation"
    """Enforce network on/off at the sandbox boundary, not by command matching."""

    HOST_DOCKER = "host_docker"
    """Reach the host Docker daemon (needed by judge-container harnesses)."""

    COMPOSE = "compose"
    """Run multi-container task topologies."""


@dataclass(frozen=True, slots=True)
class Capabilities:
    """Static, backend-class-level capability description.

    Returned by :meth:`Backend.capabilities` as a classmethod, so the values
    must not depend on a specific instance or runtime probing.
    """

    isolation: IsolationLevel
    supports_command: bool
    supports_filesystem: bool
    supports_code_interpreter: bool
    cold_start_ms_p50: int | None = None
    max_sandboxes: int | None = None
    features: frozenset[BackendCapability] = frozenset()
