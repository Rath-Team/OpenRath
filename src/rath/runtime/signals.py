"""Optional low-latency signals; never a durable Run source of truth."""

from __future__ import annotations

import json
import math
import queue
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable
from uuid import UUID

__all__ = [
    "GuardedSignalBus",
    "InMemorySignalBus",
    "RedisSignalBus",
    "RunSignal",
    "SignalBus",
    "SignalKind",
]


class SignalKind(str, Enum):
    WAKE = "wake"
    CANCEL = "cancel"


@dataclass(frozen=True, slots=True)
class RunSignal:
    kind: SignalKind
    run_id: UUID
    tenant_id: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")


@runtime_checkable
class SignalBus(Protocol):
    def publish(self, signal: RunSignal) -> None: ...

    def receive(self, *, timeout_seconds: float = 0) -> RunSignal | None: ...


class InMemorySignalBus:
    def __init__(self) -> None:
        self._queue: queue.Queue[RunSignal] = queue.Queue()

    def publish(self, signal: RunSignal) -> None:
        self._queue.put_nowait(signal)

    def receive(self, *, timeout_seconds: float = 0) -> RunSignal | None:
        try:
            return self._queue.get(timeout=timeout_seconds)
        except queue.Empty:
            return None


class RedisSignalBus:
    """Redis list transport used only to reduce polling latency."""

    def __init__(
        self,
        url: str,
        *,
        namespace: str = "openrath",
        client: object | None = None,
    ) -> None:
        if not namespace or any(char.isspace() for char in namespace):
            raise ValueError("namespace must be a non-empty token")
        if client is None:
            try:
                import redis
            except ImportError as exc:
                raise RuntimeError(
                    "Redis signaling requires `pip install openrath[redis]`"
                ) from exc
            client = redis.Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
        self.client = client
        self.key = f"{namespace}:run-signals"

    def publish(self, signal: RunSignal) -> None:
        payload = json.dumps(
            {
                "kind": signal.kind.value,
                "run_id": str(signal.run_id),
                "tenant_id": signal.tenant_id,
                "created_at": signal.created_at.isoformat(),
            },
            separators=(",", ":"),
        )
        self.client.lpush(self.key, payload)  # type: ignore[attr-defined]
        self.client.ltrim(self.key, 0, 9999)  # type: ignore[attr-defined]

    def receive(self, *, timeout_seconds: float = 0) -> RunSignal | None:
        if timeout_seconds <= 0:
            payload = self.client.rpop(self.key)  # type: ignore[attr-defined]
        else:
            timeout = max(1, math.ceil(timeout_seconds))
            result = self.client.brpop(  # type: ignore[attr-defined]
                self.key,
                timeout=timeout,
            )
            payload = result[1] if result is not None else None
        if payload is None:
            return None
        data = json.loads(payload)
        return RunSignal(
            kind=SignalKind(data["kind"]),
            run_id=UUID(data["run_id"]),
            tenant_id=data["tenant_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
        )


class GuardedSignalBus:
    """Best-effort wrapper preserving database success when Redis is unavailable."""

    def __init__(self, inner: SignalBus) -> None:
        self.inner = inner
        self.failures = 0

    def publish(self, signal: RunSignal) -> None:
        try:
            self.inner.publish(signal)
        except Exception:
            self.failures += 1

    def receive(self, *, timeout_seconds: float = 0) -> RunSignal | None:
        try:
            return self.inner.receive(timeout_seconds=timeout_seconds)
        except Exception:
            self.failures += 1
            return None
